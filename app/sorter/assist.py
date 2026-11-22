"""فرز مساعد مبني على تحليل الحركة (Optical Flow). ليس تعرّفاً على السيارات:
هو مؤشر حركة فقط، والقرار النهائي للمستخدم عندما تقل الثقة."""
from dataclasses import dataclass

from ..config.schema import SortCfg


@dataclass
class Suggestion:
    label: str          # moving | stopping | "" (غير متأكد)
    confidence: float
    score: float        # نسبة البكسلات المتحركة


def classify_score(score: float, cfg: SortCfg) -> Suggestion:
    hi, lo = cfg.moving_thr, cfg.stopping_thr
    if score >= hi:
        conf = 0.5 + 0.5 * min(1.0, (score - hi) / max(hi, 1e-9))
        return Suggestion("moving", conf, score)
    if score <= lo:
        conf = 0.5 + 0.5 * min(1.0, (lo - score) / max(lo, 1e-9))
        return Suggestion("stopping", conf, score)
    return Suggestion("", 0.0, score)


def motion_score(path, start=0.0, end=None, samples=8, width=160) -> float:
    import cv2
    import numpy as np
    cap = cv2.VideoCapture(str(path))
    try:
        if not cap.isOpened():
            raise IOError(f"Cannot open {path}")
        fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
        n = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0
        total = n / fps if n else 0
        end = min(end if end else total, total) if total else (end or 0)
        span = max(0.1, end - start)
        gap = max(2, int(fps * 0.1))
        vals = []
        for i in range(samples):
            t = start + span * (i + 0.5) / samples
            cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
            ok, a = cap.read()
            if not ok:
                continue
            for _ in range(gap - 1):
                cap.grab()
            ok, b = cap.read()
            if not ok:
                continue
            h = max(1, int(a.shape[0] * width / a.shape[1]))
            ga = cv2.cvtColor(cv2.resize(a, (width, h)), cv2.COLOR_BGR2GRAY)
            gb = cv2.cvtColor(cv2.resize(b, (width, h)), cv2.COLOR_BGR2GRAY)
            flow = cv2.calcOpticalFlowFarneback(ga, gb, None, 0.5, 2, 15, 2, 5, 1.1, 0)
            mag = np.linalg.norm(flow, axis=2)
            vals.append(float((mag > 0.4).mean()))
        if not vals:
            raise IOError("No frames could be read")
        return float(np.mean(vals))
    finally:
        cap.release()


def suggest(path, cfg: SortCfg, start=0.0, end=None) -> Suggestion:
    return classify_score(motion_score(path, start, end), cfg)
