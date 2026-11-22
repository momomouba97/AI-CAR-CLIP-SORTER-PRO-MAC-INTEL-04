"""يولّد assets/icon.png (1024x1024) بدون أي ملفات خارجية."""
import sys
from pathlib import Path
from PIL import Image, ImageDraw

S = 1024
img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
d = ImageDraw.Draw(img)
d.rounded_rectangle((40, 40, S - 40, S - 40), 210, fill=(16, 19, 24, 255))
d.rounded_rectangle((40, 40, S - 40, S - 40), 210, outline=(57, 133, 247, 255), width=14)
# شريط فيلم
for i in range(6):
    y = 150 + i * 70
    d.rounded_rectangle((100, y, 140, y + 36), 8, fill=(57, 133, 247, 255))
    d.rounded_rectangle((S - 140, y, S - 100, y + 36), 8, fill=(57, 133, 247, 255))
# سيارة
body = [(210, 640), (260, 520), (360, 450), (640, 450), (760, 520), (820, 640)]
d.polygon(body, fill=(230, 234, 240, 255))
d.polygon([(330, 520), (380, 475), (500, 475), (500, 545), (330, 545)], fill=(57, 133, 247, 255))
d.polygon([(530, 475), (630, 475), (700, 545), (530, 545)], fill=(57, 133, 247, 255))
d.rounded_rectangle((190, 610, 840, 700), 40, fill=(230, 234, 240, 255))
for cx in (330, 700):
    d.ellipse((cx - 70, 640, cx + 70, 780), fill=(16, 19, 24, 255), outline=(230, 234, 240, 255), width=14)
    d.ellipse((cx - 22, 698, cx + 22, 742), fill=(57, 133, 247, 255))
# خطوط سرعة
for i, w in enumerate((160, 110, 70)):
    d.rounded_rectangle((140, 800 + i * 34, 140 + w, 814 + i * 34), 7, fill=(40, 199, 111, 255))
out = Path(sys.argv[1] if len(sys.argv) > 1 else "assets/icon.png")
out.parent.mkdir(parents=True, exist_ok=True)
img.save(out)
print("wrote", out)
