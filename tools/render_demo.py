"""Render the docs demo (MP4, WebM, GIF) and screenshots from Orbit's real drawing code.

    python tools/render_demo.py      (needs ffmpeg)

The frames come from RingWindow._draw, so the video always matches the app.
"""

import math
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import cairo
from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
OUT = ROOT / "docs" / "assets"

from gi.repository import Gio  # noqa: E402

from orbit.app import OrbitApp  # noqa: E402
from orbit.ui import ring as R  # noqa: E402
from orbit.ui.thumbs import thumbnail  # noqa: E402

FPS, SCALE = 30, 2
CW, CH = 600, 640                       # canvas (logical px)
OX, OY = (CW - R.W) / 2, (CH - R.H) / 2  # card position on the canvas
PAPER = (0.969, 0.969, 0.961)           # #f7f7f5


def sample_photo(path: Path):
    """A synthetic sunset landscape, so the demo needs no real photos."""
    w, h = 900, 600
    img = Image.new("RGB", (w, h))
    d = ImageDraw.Draw(img)
    for y in range(h):
        t = y / h
        d.line([(0, y), (w, y)], fill=(int(255 - 60 * t), int(150 + 40 * t - 120 * t * t), int(110 + 90 * t)))
    d.ellipse((560, 170, 720, 330), fill=(255, 226, 150))
    for i, (col, base) in enumerate((((92, 70, 120), 380), ((58, 46, 86), 450), ((30, 26, 52), 520))):
        pts = [(0, h)] + [(x, base - 60 * math.sin(x / (140 + 40 * i) + i) - 30 * math.sin(x / 57 + i * 2))
                          for x in range(0, w + 10, 10)] + [(w, h)]
        d.polygon(pts, fill=col)
    img.filter(ImageFilter.GaussianBlur(0.6)).save(path)


def lerp(a, b, t):
    return a + (b - a) * t


def smooth(t):
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)


def draw_pointer(cr, x, y, dragging, thumb):
    """macOS-style arrow with a dragged file preview."""
    if dragging and thumb:
        cr.save()
        cr.translate(x + 10, y + 14)
        k = 54 / max(thumb.get_width(), thumb.get_height())
        cr.rectangle(-3, -3, thumb.get_width() * k + 6, thumb.get_height() * k + 6)
        cr.set_source_rgba(1, 1, 1, 0.9)
        cr.fill()
        cr.scale(k, k)
        cr.set_source_surface(thumb, 0, 0)
        cr.paint_with_alpha(0.85)
        cr.restore()
    cr.save()
    cr.translate(x, y)
    cr.move_to(0, 0)
    for px, py in ((0, 17), (4.2, 13), (7, 19.5), (9.6, 18.4), (6.9, 12.1), (12.2, 12.1)):
        cr.line_to(px, py)
    cr.close_path()
    cr.set_source_rgb(0.05, 0.05, 0.05)
    cr.fill_preserve()
    cr.set_source_rgb(1, 1, 1)
    cr.set_line_width(1.3)
    cr.stroke()
    cr.restore()


def card_background(cr):
    for grow, alpha in ((26, 0.05), (14, 0.07), (5, 0.09)):
        R._rounded(cr, OX - grow / 2, OY + grow / 2.5, R.W + grow, R.H + grow / 2, 24 + grow / 2)
        cr.set_source_rgba(0, 0, 0, alpha)
        cr.fill()
    R._rounded(cr, OX, OY, R.W, R.H, 24)
    cr.set_source_rgb(0.961, 0.961, 0.969)
    cr.fill_preserve()
    cr.set_source_rgba(0, 0, 0, 0.06)
    cr.set_line_width(1)
    cr.stroke()


def main():
    tmp = Path(tempfile.mkdtemp())
    photo = tmp / "Sunset.jpg"
    sample_photo(photo)
    app = OrbitApp()
    app.set_flags(app.get_flags() | Gio.ApplicationFlags.NON_UNIQUE)
    app.register(None)
    r = R.RingWindow(app, [photo])
    r.thumb = thumbnail(photo)
    import orbit.ui.sounds as snd
    snd.play = lambda *_: None
    drag_thumb = r.thumb

    def btn(i):
        x, y = r._btn_pos(i)
        return OX + x, OY + y

    def seg(i):
        sx, sy, sw, sh = r._seg_rects()[i]
        return OX + sx + sw / 2, OY + sy + sh / 2

    # Timeline: (time, pointer target, event)
    r.page = 0
    p_jpg, p_webp, p_avif = btn(0), btn(1), btn(2)
    keys = [(0.0, (40, CH - 40)), (0.9, p_jpg), (1.5, p_webp), (2.0, p_avif), (2.5, seg(1)),
            (3.2, None), (3.9, None), (4.5, None), (5.0, seg(0)), (5.7, p_webp), (6.0, p_webp)]
    total = 9.0
    frames = int(total * FPS)
    tools_targets = {}
    surf = cairo.ImageSurface(cairo.FORMAT_RGB24, CW * SCALE, CH * SCALE)
    for f in range(frames):
        t = f / FPS
        # resolve pointer targets that depend on the current page
        if r.page == 1 and not tools_targets:
            tools_targets = {3.2: btn(1), 3.9: btn(2), 4.5: btn(3)}
        pts = [(kt, tools_targets.get(kt, p) if p is None else p) for kt, p in keys]
        pts = [(kt, p) for kt, p in pts if p is not None]
        for (t0, a), (t1, b) in zip(pts, pts[1:]):
            if t0 <= t <= t1:
                k = smooth((t - t0) / (t1 - t0))
                px, py = lerp(a[0], b[0], k), lerp(a[1], b[1], k)
                break
        else:
            px, py = pts[-1][1]

        r.appear = min(1.0, t / 0.35)
        if r.mode == "menu":
            r._hover_at(px - OX, py - OY)
            if r.hover and r.hover[0] == "seg" and r.page != r.hover[1] and t > 2.6:
                r._go_page(r.hover[1])
            if t >= 6.05:
                r.start_progress("WEBP")
                r._t0 -= 0  # progress is driven below
        if r.mode == "progress":
            r.set_progress(smooth((t - 6.05) / 1.3))
            if t >= 7.45:
                r.finish(True, "Sunset.webp")
        r._animate()
        if r.mode == "done" and t > 8.4:
            r.fade = max(0.0, 1 - (t - 8.4) / 0.5)

        cr = cairo.Context(surf)
        cr.scale(SCALE, SCALE)
        cr.set_source_rgb(*PAPER)
        cr.paint()
        cr.save()
        cr.push_group()
        card_background(cr)
        cr.translate(OX, OY)
        r._draw(None, cr, R.W, R.H)
        cr.pop_group_to_source()
        cr.paint_with_alpha(max(0.0, r.fade) if r.mode == "done" else min(1.0, t / 0.35))
        cr.restore()
        draw_pointer(cr, px, py, dragging=r.mode == "menu", thumb=drag_thumb)
        surf.write_to_png(str(tmp / f"f{f:04d}.png"))
        if abs(t - 1.6) < 1 / FPS / 2:
            shutil.copy(tmp / f"f{f:04d}.png", OUT / "shot-convert.png")
        if abs(t - 3.95) < 1 / FPS / 2:
            shutil.copy(tmp / f"f{f:04d}.png", OUT / "shot-tools.png")
        if abs(t - 6.7) < 1 / FPS / 2:
            shutil.copy(tmp / f"f{f:04d}.png", OUT / "shot-progress.png")
        if abs(t - 7.9) < 1 / FPS / 2:
            shutil.copy(tmp / f"f{f:04d}.png", OUT / "shot-done.png")

    ff = ["ffmpeg", "-v", "error", "-y", "-framerate", str(FPS), "-i", str(tmp / "f%04d.png")]
    subprocess.run(ff + ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20", "-movflags", "+faststart",
                         str(OUT / "demo.mp4")], check=True)
    subprocess.run(ff + ["-c:v", "libvpx-vp9", "-b:v", "0", "-crf", "34", str(OUT / "demo.webm")], check=True)
    subprocess.run(ff + ["-vf", "fps=20,scale=480:-1:flags=lanczos,split[a][b];[a]palettegen=stats_mode=diff[p];"
                         "[b][p]paletteuse=dither=sierra2_4a", str(OUT / "demo.gif")], check=True)
    shutil.copy(photo, OUT / "sample-photo.jpg")
    shutil.rmtree(tmp)
    print("wrote", ", ".join(p.name for p in sorted(OUT.glob("demo.*"))))


if __name__ == "__main__":
    main()
