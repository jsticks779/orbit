"""Render the launch video (1080x1080, ~30 s; saved outside the repo) and the docs terminal screenshot.

    python tools/render_launch.py      (run render_demo.py and render_editors.py first)

Everything shown is real: the install command and its output, the card (demo.mp4,
rendered from the app's drawing code), the editor windows and Orbit's own sounds.
"""
import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
A = ROOT / "docs" / "assets"
SOUNDS = ROOT / "src" / "orbit" / "sounds"
GEIST = str(ROOT / "src" / "orbit" / "fonts" / "Geist-Variable.ttf")
MONO = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"
MONO_B = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"
FPS, S = 30, 1080
INK, WHITE, PAPER = (10, 10, 10), (255, 255, 255), (247, 247, 245)
SUN, GREY, DIM = (255, 214, 10), (110, 110, 108), (150, 150, 146)
TERM_BG, TERM_FG = (18, 18, 18), (232, 232, 230)

WORDMARK = [
    " ██████╗ ██████╗ ██████╗ ██╗████████╗",
    "██╔═══██╗██╔══██╗██╔══██╗██║╚══██╔══╝",
    "██║   ██║██████╔╝██████╔╝██║   ██║   ",
    "██║   ██║██╔══██╗██╔══██╗██║   ██║   ",
    "╚██████╔╝██║  ██║██████╔╝██║   ██║   ",
    " ╚═════╝ ╚═╝  ╚═╝╚═════╝ ╚═╝   ╚═╝   ",
]
CMD = "curl -fsSL https://jsticks779.github.io/orbit/install.sh | bash"
INSTALL_LINES = [
    ("Step 1 of 4 · System packages", TERM_FG),
    ("Step 2 of 4 · Downloading Orbit's components", TERM_FG),
    ("✓ Components ready", (80, 200, 120)),
    ("Step 3 of 4 · Adding Orbit to your desktop", TERM_FG),
    ("Step 4 of 4 · Drag + Shift permission", TERM_FG),
    ("✓ Already allowed", (80, 200, 120)),
]


def geist(size, weight="Black"):
    f = ImageFont.truetype(GEIST, size)
    f.set_variation_by_name(weight)
    return f


def ease(t):
    t = max(0.0, min(1.0, t))
    return 1 - (1 - t) ** 3


def centered(d, y, text, font, fill):
    w = d.textlength(text, font=font)
    d.text(((S - w) / 2, y), text, font=font, fill=fill)


# ---- scenes -------------------------------------------------------------------------

def scene_title(t):
    """0-3 s: Drag. Shift. Done."""
    im = Image.new("RGB", (S, S), WHITE)
    d = ImageDraw.Draw(im)
    big = geist(150)
    for i, word in enumerate(("Drag.", "Shift.", "Done.")):
        k = ease((t - 0.25 - i * 0.45) / 0.35)
        if k <= 0:
            continue
        y = 250 + i * 150 + (1 - k) * 40
        layer = Image.new("RGBA", (S, S), (0, 0, 0, 0))
        ImageDraw.Draw(layer).text((110, y), word, font=big, fill=INK + (int(255 * k),))
        im.paste(layer, (0, 0), layer)
    k = ease((t - 1.8) / 0.4)
    if k > 0:
        d.rounded_rectangle((110, 170, 330, 212), radius=4, fill=SUN)
        d.text((124, 178), "DRAG + SHIFT", font=ImageFont.truetype(MONO_B, 22), fill=INK)
    return im


def terminal(lines_done, typed, show_banner, cursor):
    """A plain terminal window, used by the video and the docs screenshot."""
    W, H = 960, 780
    im = Image.new("RGB", (W, H), TERM_BG)
    d = ImageDraw.Draw(im)
    d.rectangle((0, 0, W, 44), fill=(36, 36, 36))
    for i, c in enumerate(((255, 95, 87), (254, 188, 46), (40, 200, 64))):
        d.ellipse((18 + i * 24, 15, 32 + i * 24, 29), fill=c)
    d.text((W / 2 - 40, 12), "Terminal", font=ImageFont.truetype(MONO, 18), fill=DIM)
    f, fb = ImageFont.truetype(MONO, 19), ImageFont.truetype(MONO_B, 19)
    y = 66
    d.text((24, y), "$ ", font=fb, fill=SUN)
    d.text((48, y), typed + ("▌" if cursor else ""), font=f, fill=TERM_FG)
    y += 40
    for text, col in INSTALL_LINES[:lines_done]:
        d.text((24, y), text, font=fb if text.startswith("Step") else f, fill=col)
        y += 30
    if show_banner:
        y += 14
        fm = ImageFont.truetype(MONO, 22)
        for row in WORDMARK:
            x = 24
            for ch in row:
                d.text((x, y), ch, font=fm, fill=SUN if ch == "█" else (90, 90, 88))
                x += fm.getlength("█")
            y += 26
        y += 16
        d.text((24, y), "drag. shift. done.  v0.1", font=f, fill=DIM)
        d.text((24, y + 34), "●", font=f, fill=(80, 200, 120))
        d.text((48, y + 34), "Orbit is running.", font=f, fill=TERM_FG)
    return im


def scene_install(t):
    """3-10 s: the one-line install, ending with the big ORBIT."""
    im = Image.new("RGB", (S, S), PAPER)
    d = ImageDraw.Draw(im)
    centered(d, 70, "Install with one line.", geist(54, "ExtraBold"), INK)
    typed = CMD[: int(max(0, t - 0.4) * 38)]
    lines = 0 if t < 2.4 else min(len(INSTALL_LINES), int((t - 2.4) / 0.35) + 1)
    banner = t > 5.0
    term = terminal(lines, typed, banner, cursor=int(t * 2) % 2 == 0 and len(typed) < len(CMD))
    im.paste(term, ((S - term.width) // 2, 190))
    d.rectangle(((S - term.width) // 2 - 1, 189, (S + term.width) // 2, 190 + term.height), outline=(220, 220, 216))
    return im


def scene_demo(frame, t):
    """10-19 s: the real card."""
    im = Image.new("RGB", (S, S), WHITE)
    d = ImageDraw.Draw(im)
    caption = "Drag a file. Tap Shift." if t < 4.6 else "Drop. Done."
    centered(d, 70, caption, geist(54, "ExtraBold"), INK)
    fr = frame.resize((840, 896))
    im.paste(fr, ((S - 840) // 2, 160))
    return im


EDITORS = [("editor-crop.png", "Crop"), ("editor-edit.png", "Edit"),
           ("editor-addbg.png", "Add BG"), ("editor-trim.png", "Trim video")]


def scene_editors(t, shots):
    """19-24 s: the four editors."""
    im = Image.new("RGB", (S, S), PAPER)
    d = ImageDraw.Draw(im)
    i = min(len(shots) - 1, int(t / 1.25))
    centered(d, 70, f"Four small editors · {EDITORS[i][1]}", geist(50, "ExtraBold"), INK)
    shot = shots[i]
    k = ease((t - i * 1.25) / 0.3)
    x = int((S - shot.width) / 2 + (1 - k) * 60)
    im.paste(shot, (x, 170 + (820 - shot.height) // 2), shot)
    return im


def scene_end(t):
    """24-30 s: honest closing card."""
    im = Image.new("RGB", (S, S), WHITE)
    d = ImageDraw.Draw(im)
    k = ease(t / 0.5)
    icon = Image.open(A / "icon-512.png").convert("RGBA").resize((200, 200))
    im.paste(icon, ((S - 200) // 2, int(150 - (1 - k) * 20)), icon)
    centered(d, 400, "Orbit", geist(120), INK)
    centered(d, 560, "First version. Ubuntu for now.", geist(44, "SemiBold"), INK)
    centered(d, 620, "Other systems are on the way.", geist(44, "Regular"), GREY)
    centered(d, 760, "jsticks779.github.io/orbit", ImageFont.truetype(MONO_B, 34), INK)
    centered(d, 815, "Free and open source", ImageFont.truetype(MONO, 26), GREY)
    return im


def main():
    tmp = Path(tempfile.mkdtemp())
    demo_dir = tmp / "demo"
    demo_dir.mkdir()
    subprocess.run(["ffmpeg", "-v", "error", "-i", str(A / "demo.mp4"), "-vf", f"fps={FPS}",
                    str(demo_dir / "d%04d.png")], check=True)
    demo = sorted(demo_dir.glob("d*.png"))
    shots = []
    for name, _ in EDITORS:
        sh = Image.open(A / name).convert("RGBA")
        sh.thumbnail((760, 800))
        shots.append(sh)

    scenes = [(3.0, "title"), (7.0, "install"), (len(demo) / FPS, "demo"), (5.0, "editors"), (5.5, "end")]
    f = 0
    starts = {}
    t0 = 0.0
    for dur, name in scenes:
        starts[name] = t0
        for i in range(int(dur * FPS)):
            t = i / FPS
            if name == "title":
                im = scene_title(t)
            elif name == "install":
                im = scene_install(t)
            elif name == "demo":
                im = scene_demo(Image.open(demo[i]).convert("RGB"), t)
            elif name == "editors":
                im = scene_editors(t, shots)
            else:
                im = scene_end(t)
            # short cross-fade into each scene
            if i < 8 and f > 0:
                prev = Image.open(tmp / f"f{f - 1:05d}.png")
                im = Image.blend(prev, im, (i + 1) / 8)
            im.save(tmp / f"f{f:05d}.png")
            f += 1
        t0 += dur
    term = terminal(len(INSTALL_LINES), CMD, True, False)
    term.save(A / "terminal.png")

    # Orbit's real sounds at the matching moments.
    d0 = starts["demo"]
    cues = [("open", d0 + 0.1), ("switch", d0 + 2.6), ("switch", d0 + 5.0), ("start", d0 + 6.05),
            ("success", d0 + 7.45), ("success", starts["end"] + 0.2)]
    inputs, filters = [], []
    for n, (snd, at) in enumerate(cues):
        inputs += ["-i", str(SOUNDS / f"{snd}.wav")]
        filters.append(f"[{n + 1}:a]adelay={int(at * 1000)}:all=1,volume=0.9[a{n}]")
    mix = "".join(f"[a{n}]" for n in range(len(cues)))
    filters.append(f"{mix}amix=inputs={len(cues)}:normalize=0,apad[aout]")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-framerate", str(FPS), "-i", str(tmp / "f%05d.png"),
                    *inputs, "-filter_complex", ";".join(filters), "-map", "0:v", "-map", "[aout]",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20", "-c:a", "aac", "-b:a", "160k",
                    "-shortest", "-movflags", "+faststart", str(ROOT.parent / "orbit-launch" / "orbit-launch.mp4")], check=True)
    shutil.rmtree(tmp)
    print(f"launch.mp4: {f / FPS:.1f}s, terminal.png written")


if __name__ == "__main__":
    main()
