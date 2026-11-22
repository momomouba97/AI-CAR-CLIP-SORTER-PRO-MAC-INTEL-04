import os
import subprocess
import sys
from pathlib import Path


def test_selftest_passes():
    root = Path(__file__).resolve().parents[1]
    env = {**os.environ, "QT_QPA_PLATFORM": "offscreen"}
    r = subprocess.run([sys.executable, str(root / "main.py"), "--selftest"], capture_output=True, text=True,
                       env=env, cwd=root, timeout=300)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "PASSED" in r.stdout
