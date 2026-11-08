import os
import sys
import glob
from PIL import Image, ImageDraw

TG_PATH = sys.argv[1] if len(sys.argv) > 1 else "telegram"
ICON = sys.argv[2] if len(sys.argv) > 2 else "overlay/overlay/icon/icon.png"

print(f"=== Applying icon {ICON} to {TG_PATH} ===")
if not os.path.exists(ICON):
    print("Icon file not found, skipping (old icon stays)")
    sys.exit(0)

src = Image.open(ICON).convert("RGBA")
roots = [
    f"{TG_PATH}/TMessagesProj/src/main/res",
    f"{TG_PATH}/TMessagesProj/config",
    f"{TG_PATH}/TMessagesProj_App/src",
]

def find(pattern):
    out = []
    for r in roots:
        out += glob.glob(f"{r}/**/{pattern}", recursive=True)
    return out

replaced = 0
for ext in ("png", "webp"):
    for path in find(f"ic_launcher*.{ext}"):
        if "mipmap" not in path:
            continue
        with Image.open(path) as old:
            size = old.size
        img = src.resize(size, Image.LANCZOS)
        if "round" in os.path.basename(path):
            mask = Image.new("L", size, 0)
            ImageDraw.Draw(mask).ellipse((0, 0, size[0] - 1, size[1] - 1), fill=255)
            img.putalpha(mask)
        img.save(path, "PNG" if ext == "png" else "WEBP")
        replaced += 1
print(f"Replaced {replaced} icon files")

# Adaptive icons (Android 8+) point to old drawables: remove them so the new PNG is used
removed = 0
for path in find("ic_launcher*.xml"):
    if "mipmap-anydpi" in path:
        os.remove(path)
        removed += 1
        print("Removed adaptive icon:", path)
print(f"Removed {removed} adaptive icon xml files")

if replaced == 0:
    print("WARNING: no ic_launcher files found. Candidates:")
    for p in find("*launcher*")[:30]:
        print("  ", p)
