"""ينسخ ملف FFmpeg الثابت (من حزمة imageio-ffmpeg) إلى assets/bin/ffmpeg ويتحقق أنه يعمل."""
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import imageio_ffmpeg

src = Path(imageio_ffmpeg.get_ffmpeg_exe())
dst = Path("assets/bin/ffmpeg")
dst.parent.mkdir(parents=True, exist_ok=True)
shutil.copy2(src, dst)
dst.chmod(dst.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
out = subprocess.run([str(dst), "-version"], capture_output=True, text=True)
if out.returncode != 0:
    sys.exit("FFmpeg failed to run: " + out.stderr)
print(out.stdout.splitlines()[0])
enc = subprocess.run([str(dst), "-hide_banner", "-encoders"], capture_output=True, text=True).stdout
for need in ("libx264", "aac"):
    if need not in enc:
        sys.exit(f"FFmpeg lacks required encoder: {need}")
print("FFmpeg OK, size:", dst.stat().st_size)
