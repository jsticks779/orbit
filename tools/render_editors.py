"""Real screenshots of Orbit's editor windows, using real photos and a real clip.

    python tools/render_editors.py      (opens the editors for a few seconds)
"""
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
OUT = ROOT / "docs" / "assets"
PHOTOS = OUT / "photos"

from orbit.cli import _own_look  # noqa: E402

_own_look()  # before GTK loads: same light look as the real app, whatever the desktop theme

import gi  # noqa: E402

gi.require_version("Gtk", "4.0")
from gi.repository import Gio, GLib, Gtk  # noqa: E402

from orbit.app import OrbitApp  # noqa: E402
from orbit.ui import editors  # noqa: E402


def find(widget, label):
    """First button-like child with this label."""
    if isinstance(widget, (Gtk.ToggleButton, Gtk.Button)) and widget.get_label() == label:
        return widget
    child = widget.get_first_child()
    while child:
        hit = find(child, label)
        if hit:
            return hit
        child = child.get_next_sibling()
    return None


def snap(win, path):
    paintable = Gtk.WidgetPaintable.new(win)
    snapshot = Gtk.Snapshot()
    paintable.snapshot(snapshot, win.get_width(), win.get_height())
    node = snapshot.to_node()
    tex = win.get_native().get_renderer().render_texture(node, None)
    tex.save_to_png(str(path))


def main():
    tmp = Path(tempfile.mkdtemp())
    pug, berries = tmp / "Pug.jpg", tmp / "Strawberries.jpg"
    shutil.copy(PHOTOS / "pug.jpg", pug)
    shutil.copy(PHOTOS / "strawberries.jpg", berries)
    clip = tmp / "Waterfall.mp4"  # a gentle zoom over a real photo
    subprocess.run(["ffmpeg", "-v", "error", "-loop", "1", "-i", str(PHOTOS / "waterfall.jpg"), "-vf",
                    "scale=2400:-2,zoompan=z='min(zoom+0.0007,1.25)':d=1:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
                    ":s=1280x854:fps=30", "-t", "42", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(clip)],
                   check=True)

    app = OrbitApp()
    app.set_flags(app.get_flags() | Gio.ApplicationFlags.NON_UNIQUE)
    shots = []

    def setup():
        crop = editors.CropEditor(app, pug)
        crop.present()
        find(crop, "16:9").set_active(True)
        shots.append((crop, "editor-crop.png"))

        edit = editors.AdjustEditor(app, pug)
        edit.present()
        for k, v in (("warmth", 45), ("saturation", 35), ("contrast", 15), ("sharpness", 30)):
            edit.sliders[k].set_value(v)
        shots.append((edit, "editor-edit.png"))

        bg = editors.BackgroundEditor(app, berries)
        bg.present()
        bg._set(background=4)
        bg.sliders["corners"].set_value(60)
        find(bg, "1:1").set_active(True)
        shots.append((bg, "editor-addbg.png"))

        trim = editors.TrimEditor(app, clip)
        trim.present()
        trim.start.set_value(8.4)
        trim.end.set_value(27.0)
        find(trim, "2x").set_active(True)
        trim.mute.set_active(True)
        shots.append((trim, "editor-trim.png"))
        GLib.timeout_add(2500, capture)
        return False

    def capture():
        find(shots[0][0], "16:9").set_active(True)
        GLib.timeout_add(400, really_capture)
        return False

    def really_capture():
        for win, name in shots:
            snap(win, OUT / name)
            win.close()
        app.quit()
        return False

    app.connect("activate", lambda *_: None)
    app.hold()
    GLib.idle_add(setup)
    app.run([])
    shutil.rmtree(tmp)
    print("editor screenshots written")


if __name__ == "__main__":
    main()
