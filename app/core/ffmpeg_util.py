import functools
import os
import shutil
import subprocess
import sys
from pathlib import Path

from ..config.paths import app_support_dir


class FFmpegNotFound(RuntimeError):
    pass


def _bundled():
    base = getattr(sys, "_MEIPASS", None)
    if not base:
        return None
    src = Path(base) / "bin" / "ffmpeg"
    if not src.exists():
        return None
    if os.access(src, os.X_OK):
        return str(src)
    dst_dir = app_support_dir() / "bin"
    dst_dir.mkdir(parents=True, exist_ok=True)
    dst = dst_dir / "ffmpeg"
    if not dst.exists() or dst.stat().st_size != src.stat().st_size:
        shutil.copy2(src, dst)
    os.chmod(dst, 0o755)
    return str(dst)


@functools.lru_cache(maxsize=1)
def find_ffmpeg() -> str:
    env = os.environ.get("AICCS_FFMPEG")
    if env and os.path.exists(env):
        return env
    b = _bundled()
    if b:
        return b
    try:
        import imageio_ffmpeg
        exe = imageio_ffmpeg.get_ffmpeg_exe()
        if exe and os.path.exists(exe):
            return exe
    except Exception:
        pass
    w = shutil.which("ffmpeg")
    if w:
        return w
    raise FFmpegNotFound("FFmpeg not found")


@functools.lru_cache(maxsize=4)
def available_encoders(ffmpeg: str) -> frozenset:
    out = subprocess.run([ffmpeg, "-hide_banner", "-encoders"], capture_output=True, text=True, timeout=30).stdout
    names = set()
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 2 and (line.startswith(" V") or line.startswith(" A")):
            names.add(parts[1])
    return frozenset(names)


def ffmpeg_version(ffmpeg: str) -> str:
    out = subprocess.run([ffmpeg, "-version"], capture_output=True, text=True, timeout=30).stdout
    return out.splitlines()[0] if out else "unknown"
