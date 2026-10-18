"""Image conversions and quick tools (Pillow)."""

from pathlib import Path

from PIL import Image, ImageOps

from ..core.actions import TOOLS, action
from ..core.filetypes import Kind
from ..core.naming import output_path
from . import ActionError

IMG = [Kind.IMAGE]
_heif_ready = False


def open_image(path: Path) -> Image.Image:
    global _heif_ready
    if path.suffix.lower() in (".heic", ".heif") and not _heif_ready:
        _enable_heif()
    img = Image.open(path)
    return ImageOps.exif_transpose(img)


def _enable_heif():
    global _heif_ready
    try:
        from pi_heif import register_heif_opener
    except ImportError as e:
        raise ActionError("HEIC needs the pi-heif package (pip install pi-heif).") from e
    register_heif_opener()
    _heif_ready = True


def _flatten(img: Image.Image, bg=(255, 255, 255)) -> Image.Image:
    """JPG/BMP/PDF have no transparency: put the image on white."""
    if img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGBA")
        base = Image.new("RGB", img.size, bg)
        base.paste(img, mask=img.split()[-1])
        return base
    return img.convert("RGB")


def save_as(src: Path, fmt: str, suffix: str = "", img: Image.Image | None = None) -> Path:
    img = img or open_image(src)
    fmt = {"jpeg": "jpg", "tif": "tiff", "heif": "heic"}.get(fmt.lower(), fmt.lower())
    out = output_path(src, fmt, suffix)
    if fmt in ("jpg", "jpeg", "bmp", "pdf"):
        img = _flatten(img)
    elif img.mode not in ("RGB", "RGBA", "L", "LA"):
        img = img.convert("RGBA")
    if fmt == "heic":
        _enable_heif()
    opts = {
        "jpg": dict(format="JPEG", quality=92, optimize=True),
        "jpeg": dict(format="JPEG", quality=92, optimize=True),
        "webp": dict(format="WEBP", quality=90, method=6),
        "avif": dict(format="AVIF", quality=80),
        "heic": dict(format="HEIF", quality=90),
        "ico": dict(format="ICO", sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]),
        "tiff": dict(format="TIFF", compression="tiff_lzw"),
        "pdf": dict(format="PDF", resolution=150),
    }.get(fmt, dict(format=fmt.upper()))
    img.save(out, **opts)
    return out


def _converter(fmt: str, order: int):
    skip = {fmt, "jpeg"} if fmt == "jpg" else {fmt, "tif"} if fmt == "tiff" else {fmt, "heif"} if fmt == "heic" else {fmt}

    @action(f"image.to_{fmt}", fmt.upper(), IMG, skip_ext=skip, order=order)
    def convert(paths: list[Path]) -> list[Path]:
        return [save_as(p, fmt) for p in paths]


for i, f in enumerate(["jpg", "png", "webp", "avif", "heic", "tiff", "bmp", "pdf", "ico", "gif"]):
    _converter(f, i)


# ---- tools page -------------------------------------------------------------

@action("image.compress", "Compress", IMG, page=TOOLS, icon="compress", order=0)
def compress(paths):
    outs = []
    for p in paths:
        img = open_image(p)
        img.thumbnail((2560, 2560))
        fmt = "png" if p.suffix.lower() == ".png" and img.mode in ("RGBA", "LA", "P") else "jpg"
        out = output_path(p, fmt, "Compressed")
        if fmt == "png":
            img.convert("RGBA").quantize(256, method=Image.Quantize.FASTOCTREE).save(out, optimize=True)
        else:
            _flatten(img).save(out, "JPEG", quality=75, optimize=True, progressive=True)
        outs.append(out)
    return outs


@action("image.crop", "Crop", IMG, page=TOOLS, icon="crop", dialog="crop", order=1)
def crop(paths):  # handled by the crop dialog
    return []


@action("image.add_bg", "Add BG", IMG, page=TOOLS, icon="add-bg", dialog="background", order=2)
def add_bg(paths):  # handled by the background dialog
    return []


@action("image.metadata", "Metadata", IMG, page=TOOLS, icon="metadata", order=3)
def strip_metadata(paths):
    outs = []
    for p in paths:
        img = open_image(p)
        # Rebuilding from raw pixels drops EXIF, GPS, XMP and comments.
        clean = Image.frombytes(img.mode, img.size, img.tobytes())
        if img.mode == "P":
            clean.putpalette(img.getpalette())
        fmt = p.suffix.lower().lstrip(".") or "png"
        outs.append(save_as(p, fmt, "Clean", clean))
    return outs


@action("image.rotate", "Rotate", IMG, page=TOOLS, icon="rotate", order=4)
def rotate(paths):
    return [save_as(p, p.suffix.lstrip(".") or "png", "Rotated",
                    open_image(p).transpose(Image.Transpose.ROTATE_270)) for p in paths]


@action("image.resize", "Half Size", IMG, page=TOOLS, icon="resize", order=5)
def half(paths):
    outs = []
    for p in paths:
        img = open_image(p)
        img = img.resize((max(1, img.width // 2), max(1, img.height // 2)), Image.Resampling.LANCZOS)
        outs.append(save_as(p, p.suffix.lstrip(".") or "png", "Half", img))
    return outs


@action("image.grayscale", "Grayscale", IMG, page=TOOLS, icon="grayscale", order=6)
def grayscale(paths):
    return [save_as(p, p.suffix.lstrip(".") or "png", "Gray",
                    ImageOps.grayscale(open_image(p))) for p in paths]


@action("image.combine_pdf", "One PDF", IMG, icon="pdf", multi=True, order=-1)
def combine_pdf(paths):
    imgs = [_flatten(open_image(p)) for p in sorted(paths)]
    out = output_path(sorted(paths)[0], "pdf", "Combined")
    imgs[0].save(out, "PDF", resolution=150, save_all=True, append_images=imgs[1:])
    return [out]
