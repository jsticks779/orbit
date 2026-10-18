"""Before/after images for the docs, made with Orbit's own editing code.

    python tools/render_examples.py   (run render_demo.py first for the sample photo)
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
OUT = ROOT / "docs" / "assets"

from PIL import Image  # noqa: E402

from orbit.actions import backdrop  # noqa: E402
from orbit.ui.editors import adjust  # noqa: E402

src = Image.open(OUT / "sample-photo.jpg").convert("RGBA")
w, h = src.size
src.convert("RGB").save(OUT / "ex-original.jpg", quality=90)
src.crop((300, 120, 300 + 480, 120 + 270)).convert("RGB").save(OUT / "ex-crop.jpg", quality=90)
adjust(src, {"rotate": 0, "flip_h": False, "flip_v": False, "brightness": 8, "contrast": 18,
             "saturation": 45, "warmth": 55, "sharpness": 30}).convert("RGB").save(OUT / "ex-edit.jpg", quality=90)
small = src.copy()
small.thumbnail((600, 600))
for name, bg in (("ex-bg-mist.png", 0), ("ex-bg-sunset.png", 1)):
    backdrop.render(small, backdrop.Backdrop(background=bg, padding=70, corners=28, shadow=22,
                                             ratio="1:1")).convert("RGB").save(OUT / name)
print("examples written")
