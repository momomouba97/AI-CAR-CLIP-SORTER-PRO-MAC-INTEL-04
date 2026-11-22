"""تصدير المقاطع عبر FFmpeg مع تقدم حقيقي وحماية من الاستبدال والقرص الممتلئ."""
import os
import shutil
import subprocess
import time
from pathlib import Path

from ..config.schema import ExportCfg
from ..core.ffmpeg_util import available_encoders
from ..core.hooks import Hooks, Cancelled
from ..core.progress import Eta, fmt_duration
from ..core.project import Project, ClipRec

PROFILES = {
    "Fast": dict(speed="veryfast", crf=26, audio_bitrate_k=128),
    "Balanced": dict(speed="medium", crf=23, audio_bitrate_k=192),
    "High Quality": dict(speed="slow", crf=20, audio_bitrate_k=256),
    "Maximum Quality": dict(speed="slower", crf=16, audio_bitrate_k=320),
}
MIN_FREE_BYTES = 500 * 1024 * 1024


class ExportError(Exception):
    pass


class DiskFullError(ExportError):
    pass


def apply_profile(cfg: ExportCfg, name: str):
    p = PROFILES[name]
    cfg.profile = name
    cfg.speed, cfg.crf, cfg.audio_bitrate_k = p["speed"], p["crf"], p["audio_bitrate_k"]
    cfg.bitrate_k = 0


def default_threads(cfg: ExportCfg) -> int:
    return cfg.threads if cfg.threads > 0 else max(2, (os.cpu_count() or 4) // 2)


def build_command(ffmpeg, src, dst, start, duration, cfg: ExportCfg, threads=0):
    cmd = [ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-nostdin", "-progress", "pipe:1", "-nostats",
           "-ss", f"{start:.3f}", "-i", str(src), "-t", f"{duration:.3f}", "-map", "0:v:0"]
    if cfg.keep_audio:
        cmd += ["-map", "0:a:0?"]
    if cfg.fast_copy:
        cmd += ["-c", "copy", "-avoid_negative_ts", "make_zero"]
    else:
        cmd += ["-c:v", "libx265" if cfg.codec == "h265" else "libx264", "-preset", cfg.speed]
        cmd += ["-b:v", f"{cfg.bitrate_k}k"] if cfg.bitrate_k > 0 else ["-crf", str(cfg.crf)]
        if cfg.codec == "h265":
            cmd += ["-tag:v", "hvc1"]
        if cfg.height > 0:
            cmd += ["-vf", f"scale=-2:{cfg.height}"]
        if cfg.fps > 0:
            cmd += ["-r", str(cfg.fps)]
        cmd += ["-pix_fmt", "yuv420p"]
        if cfg.keep_audio:
            cmd += ["-c:a", cfg.audio_codec]
            if cfg.audio_codec != "copy":
                cmd += ["-b:a", f"{cfg.audio_bitrate_k}k"]
        if threads:
            cmd += ["-threads", str(threads)]
    if not cfg.keep_audio:
        cmd += ["-an"]
    cmd += ["-movflags", "+faststart", str(dst)]
    return cmd


def check_encoder(ffmpeg, cfg: ExportCfg):
    if cfg.fast_copy:
        return
    enc = "libx265" if cfg.codec == "h265" else "libx264"
    if enc not in available_encoders(ffmpeg):
        raise ExportError(f"Encoder {enc} is not available in this FFmpeg build")


def unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    i = 1
    while True:
        cand = path.with_name(f"{path.stem}_{i}{path.suffix}")
        if not cand.exists():
            return cand
        i += 1


def _move_to_trash(project: Project, f: Path):
    Path(project.trash_dir).mkdir(parents=True, exist_ok=True)
    dst = unique_path(Path(project.trash_dir) / f.name)
    shutil.move(str(f), str(dst))


def run_ffmpeg(cmd, duration, hooks: Hooks, on_frac=None):
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
    errors = []
    try:
        for line in proc.stdout:
            line = line.strip()
            if line.startswith(("out_time_us=", "out_time_ms=")):
                try:
                    sec = int(line.split("=", 1)[1]) / 1e6
                    if on_frac and duration > 0:
                        on_frac(min(1.0, max(0.0, sec / duration)))
                except ValueError:
                    pass
            elif "=" not in line and line:
                errors.append(line)
            if hooks.cancel.is_set():
                proc.terminate()
                break
        proc.wait(timeout=30)
    except Exception:
        proc.kill()
        raise
    if hooks.cancel.is_set():
        raise Cancelled()
    if proc.returncode != 0:
        raise ExportError("; ".join(errors[-5:]) or f"ffmpeg exit code {proc.returncode}")


def export_clip(ffmpeg, project: Project, clip: ClipRec, hooks: Hooks, on_frac=None):
    cfg = project.export
    src = Path(clip.source)
    if not src.is_file():
        raise ExportError(f"Source missing: {src}")
    out_dir = Path(project.paths.export)
    out_dir.mkdir(parents=True, exist_ok=True)
    ext = "." + cfg.container
    dst = out_dir / f"{clip.name}{ext}"
    if dst.exists():
        if cfg.existing == "skip":
            clip.file, clip.exported = str(dst), True
            return "skipped"
        if cfg.existing == "overwrite":
            _move_to_trash(project, dst)   # لا حذف نهائي: النسخة القديمة تنتقل إلى .trash
        else:
            dst = unique_path(dst)
    est = int(src.stat().st_size * min(1.0, clip.duration / max(1.0, _src_dur(project, clip))) * 1.5)
    free = shutil.disk_usage(out_dir).free
    if free < max(MIN_FREE_BYTES, est):
        raise DiskFullError(f"Not enough disk space ({free // 2**20} MB free)")
    part = dst.with_name(dst.stem + ".part" + dst.suffix)
    cmd = build_command(ffmpeg, src, part, clip.start, clip.duration, cfg, default_threads(cfg))
    try:
        run_ffmpeg(cmd, clip.duration, hooks, on_frac)
        if not part.exists() or part.stat().st_size == 0:
            raise ExportError("Empty output file")
        os.replace(part, dst)
    except BaseException:
        if part.exists():
            try:
                part.unlink()
            except OSError:
                pass
        raise
    clip.file, clip.exported, clip.error = str(dst), True, ""
    return "exported"


def _src_dur(project, clip):
    v = project.video(clip.source)
    return v.duration if v and v.duration else clip.end


def export_clips(ffmpeg, project: Project, clips, hooks: Hooks, save=None):
    """يصدّر قائمة مقاطع. يعيد dict بالنتائج. يحفظ المشروع بعد كل مقطع."""
    check_encoder(ffmpeg, project.export)
    todo = [c for c in clips if not (c.exported and c.file and os.path.isfile(c.file))]
    res = {"done": 0, "skipped": 0, "failed": 0, "total": len(todo), "errors": []}
    eta = Eta()
    for i, clip in enumerate(todo):
        hooks.check()
        base = i / max(1, len(todo))

        def on_frac(f, i=i, clip=clip):
            overall = (i + f) / len(todo)
            hooks.progress("export", overall,
                           f"{i + 1}/{len(todo)} • {clip.name} • ETA {fmt_duration(eta.remaining(overall))}")
        hooks.progress("export", base, f"{i + 1}/{len(todo)} • {clip.name}")
        try:
            r = export_clip(ffmpeg, project, clip, hooks, on_frac)
            res["skipped" if r == "skipped" else "done"] += 1
            if r != "skipped":
                project.bump("exported")
            hooks.log(f"Exported: {clip.name}", "success")
        except Cancelled:
            raise
        except DiskFullError as e:
            clip.error = str(e)
            hooks.log(str(e), "error")
            if save:
                save()
            raise
        except Exception as e:
            clip.error = str(e)
            res["failed"] += 1
            res["errors"].append(f"{clip.name}: {e}")
            hooks.log(f"Export failed {clip.name}: {e}", "error")
        if save:
            save()
    write_index(project)
    return res


def write_index(project: Project):
    import json
    rows = [{"file": c.file, "source": c.source, "index": c.index, "start": c.start, "end": c.end,
             "duration": c.duration, "category": c.category} for c in project.clips if c.exported]
    try:
        Path(project.paths.export).mkdir(parents=True, exist_ok=True)
        (Path(project.paths.export) / "clips_index.json").write_text(
            json.dumps(rows, ensure_ascii=False, indent=1), "utf-8")
    except OSError:
        pass


def cleanup_partials(project: Project):
    """حذف ملفات .part المتبقية من عملية انقطعت (ملفاتنا نحن فقط)."""
    d = Path(project.paths.export)
    if d.is_dir():
        for f in d.glob("*.part.*"):
            try:
                f.unlink()
            except OSError:
                pass
