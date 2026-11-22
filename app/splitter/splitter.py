"""اكتشاف المشاهد وتقسيم الفيديو وتخطيط المقاطع."""
import math
import threading
import time

from ..core.hooks import Hooks, Cancelled
from ..core.project import Project, VideoRec, SceneRec, ClipRec, new_clip_id
from ..config.schema import AnalysisCfg
from pathlib import Path

EPS = 1e-6


# ---------- دوال نقية (قابلة للاختبار) ----------
def fixed_segments(duration: float, seg_len: float):
    seg_len = max(0.5, seg_len)
    out, t = [], 0.0
    while t < duration - EPS:
        out.append((t, min(duration, t + seg_len)))
        t += seg_len
    return out


def merge_short(segs, min_len):
    """دمج المقاطع الأقصر من min_len مع الجار (السابق، أو التالي للأول)."""
    segs = [list(s) for s in segs]
    i = 0
    while i < len(segs) and len(segs) > 1:
        if segs[i][1] - segs[i][0] < min_len - EPS:
            if i > 0:
                segs[i - 1][1] = segs[i][1]
                del segs[i]
            else:
                segs[1][0] = segs[0][0]
                del segs[0]
            i = max(0, i - 1)
        else:
            i += 1
    return [tuple(s) for s in segs]


def group_to_target(segs, target):
    """دمج المشاهد المتتالية حتى تبلغ المجموعة المدة المستهدفة تقريباً."""
    if target <= 0 or not segs:
        return list(segs)
    out, cur = [], None
    for s, e in segs:
        if cur is None:
            cur = [s, e]
        elif (cur[1] - cur[0]) < target and (e - cur[0]) <= target * 1.25:
            cur[1] = e
        else:
            out.append(tuple(cur))
            cur = [s, e]
    if cur:
        out.append(tuple(cur))
    return out


def split_long(segs, max_len):
    if max_len <= 0:
        return list(segs)
    out = []
    for s, e in segs:
        d = e - s
        if d <= max_len + EPS:
            out.append((s, e))
            continue
        n = math.ceil(d / max_len - EPS)
        step = d / n
        out.extend((s + i * step, s + (i + 1) * step if i < n - 1 else e) for i in range(n))
    return out


def post_process(segs, cfg: AnalysisCfg):
    segs = sorted((float(s), float(e)) for s, e in segs if e - s > EPS)
    segs = merge_short(segs, cfg.min_scene_len) if cfg.min_scene_len > 0 else segs
    segs = group_to_target(segs, cfg.target_len)
    segs = split_long(segs, cfg.max_scene_len)
    return [(s, e) for s, e in segs if e - s >= cfg.min_valid_len]


def merge_scenes(scenes, indices):
    """دمج مشاهد متجاورة محددة بالفهارس في مشهد واحد."""
    idx = sorted(set(indices))
    if len(idx) < 2:
        return scenes
    if idx != list(range(idx[0], idx[-1] + 1)):
        raise ValueError("Scenes to merge must be adjacent")
    merged = SceneRec(scenes[idx[0]].start, scenes[idx[-1]].end, True)
    return scenes[:idx[0]] + [merged] + scenes[idx[-1] + 1:]


# ---------- الاكتشاف عبر PySceneDetect ----------
def detect_scenes(video: VideoRec, cfg: AnalysisCfg, hooks: Hooks):
    from scenedetect import open_video, SceneManager, ContentDetector, AdaptiveDetector
    vs = open_video(video.path)
    sm = SceneManager()
    min_frames = max(1, int(round(cfg.min_scene_len * (video.fps or 25))))
    if cfg.detector == "adaptive":
        sm.add_detector(AdaptiveDetector(adaptive_threshold=cfg.adaptive_threshold, min_scene_len=min_frames))
    else:
        sm.add_detector(ContentDetector(threshold=cfg.threshold, min_scene_len=min_frames))
    total = max(1, int(video.duration * (video.fps or 25)))
    stop = threading.Event()

    def poll():  # تقدم حقيقي مبني على الإطار الحالي
        while not stop.wait(0.4):
            try:
                frac = min(0.99, vs.frame_number / total)
            except Exception:
                frac = None
            hooks.progress("detect", frac, f"{video.name} • {int((frac or 0) * 100)}%")
            if hooks.cancel.is_set():
                sm.stop()

    t = threading.Thread(target=poll, daemon=True)
    t.start()
    try:
        sm.detect_scenes(vs, show_progress=False)
    finally:
        stop.set()
        t.join(timeout=2)
    if hooks.cancel.is_set():
        raise Cancelled()
    scenes = [(s.get_seconds(), e.get_seconds()) for s, e in sm.get_scene_list()]
    return scenes or [(0.0, video.duration)]


def analyze_video(video: VideoRec, cfg: AnalysisCfg, hooks: Hooks):
    """يعيد قائمة (start,end) النهائية حسب وضع التقسيم."""
    if cfg.mode == "fixed":
        raw = fixed_segments(video.duration, cfg.fixed_len)
        return post_process(raw, AnalysisCfg(min_scene_len=0, min_valid_len=cfg.min_valid_len))
    raw = detect_scenes(video, cfg, hooks)
    if cfg.mode == "auto_short":
        c = AnalysisCfg(**{**cfg.__dict__, "max_scene_len": cfg.target_len or cfg.fixed_len, "target_len": 0})
        return post_process(raw, c)
    return post_process(raw, cfg)


def set_scenes(video: VideoRec, segs, manual=False):
    video.scenes = [SceneRec(s, e, True) for s, e in segs]
    video.scenes_manual = manual
    video.status = "analyzed"
    video.done_steps = [s for s in video.done_steps if s not in ("split", "export", "complete")]


# ---------- تخطيط المقاطع ----------
def clip_name(cfg: AnalysisCfg, video: VideoRec, n: int) -> str:
    return f"{cfg.prefix}_{Path(video.path).stem}_{n:04d}"


def plan_clips(project: Project, video: VideoRec):
    """ينشئ ClipRec للمشاهد المحتفظ بها. المقاطع المصدّرة سابقاً تبقى كما هي."""
    keep_ids = {c.id for c in project.clips if c.source != video.path or c.exported}
    project.clips = [c for c in project.clips if c.id in keep_ids]
    existing = {(c.source, c.index) for c in project.clips if c.source == video.path}
    created = 0
    for n, sc in enumerate(video.scenes, start=1):
        if not sc.keep or (video.path, n) in existing:
            continue
        project.clips.append(ClipRec(new_clip_id(), video.path, n, sc.start, sc.end,
                                     name=clip_name(project.analysis, video, n)))
        created += 1
    return created
