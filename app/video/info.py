import os
from pathlib import Path

VIDEO_EXTS = {".mp4", ".mov", ".m4v", ".mkv", ".avi", ".mts", ".m2ts", ".webm", ".mpg", ".mpeg", ".wmv", ".flv"}


class CorruptVideoError(Exception):
    pass


def natural_key(path):
    """ترتيب طبيعي: clip2 قبل clip10."""
    import re
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", str(path))]


def is_video(path) -> bool:
    return Path(path).suffix.lower() in VIDEO_EXTS


def scan_folder(folder, recursive=True):
    out = []
    if recursive:
        for root, _dirs, files in os.walk(folder):
            for f in sorted(files):
                if not f.startswith(".") and is_video(f):
                    out.append(str(Path(root) / f))
    else:
        for f in sorted(os.listdir(folder)):
            p = Path(folder) / f
            if p.is_file() and not f.startswith(".") and is_video(f):
                out.append(str(p))
    return sorted(out, key=natural_key)


def probe(path) -> dict:
    """قراءة بيانات الفيديو عبر OpenCV. يرفع CorruptVideoError للملفات التالفة."""
    import cv2
    if not os.path.isfile(path):
        raise CorruptVideoError(f"File not found: {path}")
    cap = cv2.VideoCapture(str(path))
    try:
        if not cap.isOpened():
            raise CorruptVideoError(f"Cannot open: {path}")
        fps = cap.get(cv2.CAP_PROP_FPS) or 0.0
        frames = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0.0
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
        if fps <= 0 or frames <= 0 or w <= 0 or h <= 0:
            raise CorruptVideoError(f"Invalid video metadata: {path}")
        ok, _ = cap.read()
        if not ok:
            raise CorruptVideoError(f"Cannot decode first frame: {path}")
    finally:
        cap.release()
    return {"duration": frames / fps, "fps": fps, "width": w, "height": h, "size": os.path.getsize(path)}
