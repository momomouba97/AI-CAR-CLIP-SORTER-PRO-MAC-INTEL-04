#!/bin/bash
# يحوّل assets/icon.png إلى assets/icon.icns (يعمل على macOS فقط)
set -euo pipefail
cd "$(dirname "$0")/.."
SET=assets/icon.iconset
rm -rf "$SET" && mkdir -p "$SET"
for s in 16 32 128 256 512; do
  sips -z $s $s assets/icon.png --out "$SET/icon_${s}x${s}.png" >/dev/null
  sips -z $((s*2)) $((s*2)) assets/icon.png --out "$SET/icon_${s}x${s}@2x.png" >/dev/null
done
iconutil -c icns "$SET" -o assets/icon.icns
rm -rf "$SET"
echo "created assets/icon.icns"
