"""Small previews for the panel centre: images, first PDF page, video frame."""

import io
import subprocess
from pathlib import Path

import cairo

from ..core.filetypes import Kind, kind_of

SIZE = 192


def _png_to_surface(data: bytes):
    return cairo.ImageSurface.create_from_png(io.BytesIO(data)) if data else None


def thumbnail(path: Path):
    """Return a cairo ImageSurface or None. Safe to call from a worker thread."""
    try:
        kind = kind_of(path)
        if kind == Kind.IMAGE:
            from ..actions.image import open_image
            img = open_image(path)
            img.thumbnail((SIZE, SIZE))
            buf = io.BytesIO()
            img.convert("RGBA").save(buf, "PNG")
            return _png_to_surface(buf.getvalue())
        if kind == Kind.PDF:
            import pymupdf
            page = pymupdf.open(path)[0]
            zoom = SIZE / max(page.rect.width, page.rect.height)
            return _png_to_surface(page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom)).tobytes("png"))
        if kind == Kind.VIDEO:
            png = subprocess.run(["ffmpeg", "-v", "error", "-ss", "1", "-i", str(path), "-frames:v", "1",
                                  "-vf", f"scale={SIZE}:-2", "-f", "image2pipe", "-c:v", "png", "-"],
                                 capture_output=True, timeout=8).stdout
            return _png_to_surface(png)
    except Exception:
        return None
    return None
