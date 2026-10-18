"""Small editor windows opened from the ring: Crop and Add BG."""

import io
from pathlib import Path

import cairo
import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gdk, GLib, Gtk  # noqa: E402
from PIL import Image  # noqa: E402

from ..actions import backdrop  # noqa: E402
from ..actions.image import open_image, save_as  # noqa: E402

PREVIEW = 520   # longest side of the on-screen preview (px)
HANDLE = 9


def to_texture(img: Image.Image) -> Gdk.Texture:
    buf = io.BytesIO()
    img.save(buf, "PNG", compress_level=1)
    return Gdk.Texture.new_from_bytes(GLib.Bytes.new(buf.getvalue()))


class _Editor(Gtk.Window):
    def __init__(self, app, path: Path, title: str, apply_label: str):
        super().__init__(application=app, title=title, default_width=600, resizable=False)
        self.app, self.path = app, path
        self.add_css_class("orbit-editor")
        self.img = open_image(path)

        header = Gtk.HeaderBar()
        self.set_titlebar(header)
        self.body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14,
                            margin_top=16, margin_bottom=16, margin_start=18, margin_end=18)
        self.set_child(self.body)

        self.footer = Gtk.Box(spacing=8)
        reset = Gtk.Button(label="Reset")
        reset.connect("clicked", lambda *_: self.reset())
        apply = Gtk.Button(label=apply_label, hexpand=True, halign=Gtk.Align.END)
        apply.add_css_class("suggested-action")
        apply.connect("clicked", lambda *_: self._apply())
        self.footer.append(reset)
        self.footer.append(apply)

        keys = Gtk.EventControllerKey()
        keys.connect("key-pressed", lambda _c, k, *_: (self.close(), True)[1] if k == Gdk.KEY_Escape else False)
        self.add_controller(keys)

    def row(self, label: str, widget: Gtk.Widget) -> Gtk.Box:
        box = Gtk.Box(spacing=12)
        lab = Gtk.Label(label=label, xalign=0, width_chars=12)
        lab.add_css_class("dim-label")
        box.append(lab)
        widget.set_hexpand(True)
        box.append(widget)
        return box

    def chips(self, names, active, on_pick) -> Gtk.Box:
        box = Gtk.Box(spacing=4)
        box.add_css_class("linked")
        first = None
        for name in names:
            b = Gtk.ToggleButton(label=name, group=first)
            first = first or b
            b.set_active(name == active)
            b.connect("toggled", lambda btn, n=name: btn.get_active() and on_pick(n))
            box.append(b)
        return box

    def _apply(self):
        out = self.save()
        self.close()
        self.app.done([out])


# ---- Crop ------------------------------------------------------------------------

class CropEditor(_Editor):
    ASPECTS = {"Free": None, "1:1": 1, "16:9": 16 / 9, "9:16": 9 / 16, "4:3": 4 / 3, "3:4": 3 / 4}

    def __init__(self, app, path: Path):
        super().__init__(app, path, "Crop Image", "Apply")
        W, H = self.img.size
        self.scale = min(PREVIEW / W, PREVIEW / H, 1.0)
        buf = io.BytesIO()
        self.img.resize((round(W * self.scale), round(H * self.scale))).save(buf, "PNG")
        buf.seek(0)
        self.surface = cairo.ImageSurface.create_from_png(buf)
        self.aspect = None
        self.drag = None

        self.area = Gtk.DrawingArea(content_width=round(W * self.scale), content_height=round(H * self.scale),
                                    halign=Gtk.Align.CENTER)
        self.area.set_draw_func(self._draw)
        drag = Gtk.GestureDrag()
        drag.connect("drag-begin", self._begin)
        drag.connect("drag-update", self._update)
        self.area.add_controller(drag)
        self.body.append(self.area)

        self.body.append(self.row("Aspect ratio", self.chips(self.ASPECTS, "Free", self._set_aspect)))
        self.w_spin = Gtk.SpinButton.new_with_range(1, W, 1)
        self.h_spin = Gtk.SpinButton.new_with_range(1, H, 1)
        size = Gtk.Box(spacing=8)
        for lab, spin in (("W", self.w_spin), ("H", self.h_spin)):
            size.append(Gtk.Label(label=lab))
            size.append(spin)
            spin.connect("value-changed", self._typed)
        size.append(Gtk.Label(label="px"))
        self.body.append(self.row("Size", size))
        self.body.append(self.footer)
        self.reset()

    def reset(self):
        W, H = self.img.size
        self.rect = [0.0, 0.0, float(W), float(H)]  # x, y, w, h in image pixels
        self._sync()

    def _set_aspect(self, name):
        self.aspect = self.ASPECTS[name]
        if self.aspect:
            x, y, w, h = self.rect
            nw, nh = (w, w / self.aspect) if w / self.aspect <= h else (h * self.aspect, h)
            self.rect = [x + (w - nw) / 2, y + (h - nh) / 2, nw, nh]
            self._sync()

    def _typed(self, *_):
        if getattr(self, "_syncing", False):
            return
        W, H = self.img.size
        x, y, _, _ = self.rect
        w, h = self.w_spin.get_value(), self.h_spin.get_value()
        self.rect = [min(x, W - w), min(y, H - h), w, h]
        self.area.queue_draw()

    def _sync(self):
        self._syncing = True
        self.w_spin.set_value(round(self.rect[2]))
        self.h_spin.set_value(round(self.rect[3]))
        self._syncing = False
        self.area.queue_draw()

    def _begin(self, _g, x, y):
        s = self.scale
        rx, ry, rw, rh = (v * s for v in self.rect)
        near = lambda a, b: abs(a - b) <= HANDLE * 1.6  # noqa: E731
        edges = ("l" if near(x, rx) else "r" if near(x, rx + rw) else "") + \
                ("t" if near(y, ry) else "b" if near(y, ry + rh) else "")
        inside = rx < x < rx + rw and ry < y < ry + rh
        self.drag = (edges or ("move" if inside else None), list(self.rect))

    def _update(self, _g, dx, dy):
        if not self.drag or not self.drag[0]:
            return
        mode, (x, y, w, h) = self.drag
        dx, dy = dx / self.scale, dy / self.scale
        W, H = self.img.size
        if mode == "move":
            x, y = min(max(0, x + dx), W - w), min(max(0, y + dy), H - h)
        else:
            if "l" in mode:
                nx = min(max(0, x + dx), x + w - 10)
                w, x = w + (x - nx), nx
            if "r" in mode:
                w = min(max(10, w + dx), W - x)
            if "t" in mode:
                ny = min(max(0, y + dy), y + h - 10)
                h, y = h + (y - ny), ny
            if "b" in mode:
                h = min(max(10, h + dy), H - y)
            if self.aspect:
                if mode in ("t", "b"):
                    w = min(h * self.aspect, W - x)
                else:
                    h = min(w / self.aspect, H - y)
                    w = h * self.aspect
        self.rect = [x, y, w, h]
        self._sync()

    def _draw(self, _a, cr, w, h):
        cr.set_source_surface(self.surface, 0, 0)
        cr.paint()
        x, y, rw, rh = (v * self.scale for v in self.rect)
        # Dim everything outside the crop.
        cr.set_source_rgba(0, 0, 0, 0.5)
        cr.rectangle(0, 0, w, h)
        cr.rectangle(x, y, rw, rh)
        cr.set_fill_rule(cairo.FILL_RULE_EVEN_ODD)
        cr.fill()
        cr.set_source_rgb(0.91, 0.29, 0.18)
        cr.set_line_width(2)
        cr.rectangle(x, y, rw, rh)
        cr.stroke()
        for hx in (x, x + rw / 2, x + rw):
            for hy in (y, y + rh / 2, y + rh):
                if (hx, hy) != (x + rw / 2, y + rh / 2):
                    cr.rectangle(hx - HANDLE / 2, hy - HANDLE / 2, HANDLE, HANDLE)
        cr.fill()

    def save(self) -> Path:
        x, y, w, h = (round(v) for v in self.rect)
        return save_as(self.path, self.path.suffix.lstrip(".") or "png", "Cropped",
                       self.img.crop((x, y, x + w, y + h)))


# ---- Add background ----------------------------------------------------------------

class BackgroundEditor(_Editor):
    def __init__(self, app, path: Path):
        super().__init__(app, path, "Add BG", "Save with Background")
        self.opt = backdrop.Backdrop()
        # Preview works on a small copy; settings scale to match.
        self.small = self.img.copy()
        self.small.thumbnail((PREVIEW, PREVIEW))
        self.k = self.small.width / self.img.width
        self._pending = None

        self.picture = Gtk.Picture(content_fit=Gtk.ContentFit.CONTAIN, height_request=360)
        self.picture.add_css_class("orbit-preview")
        self.body.append(self.picture)

        swatches = Gtk.FlowBox(max_children_per_line=10, selection_mode=Gtk.SelectionMode.NONE,
                               column_spacing=6, row_spacing=6)
        for i, (c1, c2, _) in enumerate(backdrop.GRADIENTS):
            swatches.append(self._swatch(f"linear-gradient(135deg, {c1}, {c2})", i))
        for c in backdrop.SOLIDS:
            swatches.append(self._swatch(c, c))
        self.body.append(self.row("Background", swatches))

        self.sliders = {}
        for name, hi in (("padding", 800), ("corners", 300), ("shadow", 80)):
            s = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, hi, 1)
            s.set_draw_value(True)
            s.set_value_pos(Gtk.PositionType.RIGHT)
            s.connect("value-changed", self._slid, name)
            self.sliders[name] = s
            self.body.append(self.row(name.title(), s))
        self.body.append(self.row("Ratio", self.chips(list(backdrop.RATIOS)[:4], "Auto", self._ratio)))
        self.body.append(self.footer)
        self.reset()

    def _swatch(self, css_bg, value):
        b = Gtk.Button(width_request=30, height_request=30)
        b.add_css_class("orbit-swatch")
        prov = Gtk.CssProvider()
        prov.load_from_string(f"button {{ background: {css_bg}; }}")
        b.get_style_context().add_provider(prov, Gtk.STYLE_PROVIDER_PRIORITY_USER)
        b.connect("clicked", lambda *_: self._set(background=value))
        return b

    def reset(self):
        self.opt = backdrop.Backdrop(padding=round(min(self.img.size) * 0.08))
        for name, s in self.sliders.items():
            s.set_value(getattr(self.opt, name))
        self._refresh()

    def _slid(self, scale, name):
        self._set(**{name: int(scale.get_value())})

    def _ratio(self, name):
        self._set(ratio=name)

    def _set(self, **kw):
        for k, v in kw.items():
            setattr(self.opt, k, v)
        if not self._pending:  # coalesce fast slider moves
            self._pending = GLib.timeout_add(40, self._refresh)

    def _refresh(self):
        self._pending = None
        o = self.opt
        small = backdrop.Backdrop(o.background, round(o.padding * self.k), round(o.corners * self.k),
                                  round(o.shadow * self.k), o.ratio)
        self.picture.set_paintable(to_texture(backdrop.render(self.small, small)))
        return False

    def save(self) -> Path:
        return save_as(self.path, "png", "With Background", backdrop.render(self.img, self.opt))


EDITORS = {"crop": CropEditor, "background": BackgroundEditor}
