"""Put an image on a pretty background: padding, rounded corners, shadow, ratio.

Pure Pillow so the editor preview and the saved file are pixel-identical.
"""

from dataclasses import dataclass

from PIL import Image, ImageDraw, ImageFilter, ImageOps

GRADIENTS = [
    ("#ff5f6d", "#ffc371", "#ff9a5a"),   # sunset (default, like the video)
    ("#a1c4fd", "#c2e9fb", "#b1d6fc"),   # sky
    ("#f093fb", "#f5576c", "#f37bb3"),   # pink
    ("#43e97b", "#38f9d7", "#3ef1a9"),   # mint
    ("#fa709a", "#fee140", "#fca86d"),   # peach
    ("#667eea", "#764ba2", "#6e65c6"),   # violet
    ("#0f2027", "#2c5364", "#203a43"),   # night
    ("#ff9a9e", "#fecfef", "#fdb4c7"),   # blush
]
SOLIDS = ["#ffffff", "#f4c542", "#8bc34a", "#2e9e5b", "#26a69a", "#4dd0e1", "#3f51b5", "#263238", "#7e57c2"]
RATIOS = {"Auto": None, "1:1": 1.0, "16:9": 16 / 9, "4:5": 4 / 5, "9:16": 9 / 16}


@dataclass
class Backdrop:
    background: int | str = 0     # index into GRADIENTS, or a "#rrggbb" solid
    padding: int = 160
    corners: int = 48
    shadow: int = 24
    ratio: str = "Auto"


def _fill(size, bg) -> Image.Image:
    if isinstance(bg, str):
        return Image.new("RGB", size, bg)
    c1, c2, mid = GRADIENTS[bg % len(GRADIENTS)]
    ramp = Image.linear_gradient("L").rotate(45, expand=True, resample=Image.Resampling.BICUBIC)
    ramp = ImageOps.crop(ramp, border=ramp.width // 4).resize(size, Image.Resampling.BICUBIC)
    return ImageOps.colorize(ramp, black=c1, white=c2, mid=mid)


def render(img: Image.Image, opt: Backdrop) -> Image.Image:
    img = img.convert("RGBA")
    w, h = img.size
    cw, ch = w + 2 * opt.padding, h + 2 * opt.padding
    want = RATIOS.get(opt.ratio)
    if want:
        if cw / ch < want:
            cw = round(ch * want)
        else:
            ch = round(cw / want)
    canvas = _fill((cw, ch), opt.background).convert("RGBA")
    x, y = (cw - w) // 2, (ch - h) // 2

    radius = min(opt.corners, w // 2, h // 2)
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, w - 1, h - 1), radius=radius, fill=255)

    if opt.shadow > 0:
        shadow = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
        dy = opt.shadow // 3
        ImageDraw.Draw(shadow).rounded_rectangle((x, y + dy, x + w, y + h + dy), radius=radius,
                                                 fill=(0, 0, 0, 110))
        canvas = Image.alpha_composite(canvas, shadow.filter(ImageFilter.GaussianBlur(opt.shadow)))

    alpha = img.getchannel("A")
    mask = Image.composite(alpha, Image.new("L", (w, h), 0), mask)
    canvas.paste(img, (x, y), mask)
    return canvas
