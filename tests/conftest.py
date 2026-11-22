import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(autouse=True)
def _home(tmp_path, monkeypatch):
    monkeypatch.setenv("AICCS_HOME", str(tmp_path / "home"))


@pytest.fixture(scope="session")
def ffmpeg():
    from app.core.ffmpeg_util import find_ffmpeg
    return find_ffmpeg()


def make_video(path, ffmpeg, colors=("red", "blue", "green"), d=3, size="320x240"):
    ins = []
    for c in colors:
        ins += ["-f", "lavfi", "-t", str(d), "-i", f"color=c={c}:s={size}:r=25"]
    flt = "".join(f"[{i}:v]" for i in range(len(colors))) + f"concat=n={len(colors)}:v=1:a=0[v]"
    subprocess.run([ffmpeg, "-y", "-loglevel", "error", *ins, "-filter_complex", flt, "-map", "[v]",
                    "-pix_fmt", "yuv420p", "-c:v", "libx264", str(path)], check=True)


@pytest.fixture
def video3(tmp_path, ffmpeg):
    p = tmp_path / "three.mp4"
    make_video(p, ffmpeg)
    return str(p)
