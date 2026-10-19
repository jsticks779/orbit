"""The Orbit panel: a compact floating card with a circle of actions.

macOS / iOS inspired: a light or dark material card, an iOS segmented control
(Convert / Tools), round buttons on an orbit, a live file preview in the middle
and a one-line explanation at the bottom. After a choice the same card shows
real progress, then a ✓ (and closes itself) or ✗.

Wayland doesn't let apps place windows, so the bundled GNOME Shell extension
(data/gnome-extension) moves the card to the pointer. Without it GNOME
decides where the card appears.
"""

import logging
import math
import threading
import time
from pathlib import Path

import cairo
import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("PangoCairo", "1.0")
gi.require_version("GdkPixbuf", "2.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, GdkPixbuf, GLib, Gtk, Pango, PangoCairo  # noqa: E402

from ..core.actions import Action, pages_for  # noqa: E402
from ..core.portal import real_paths  # noqa: E402
from . import sounds  # noqa: E402
from .thumbs import thumbnail  # noqa: E402

log = logging.getLogger("orbit")

W, H = 396, 512          # the window is the card
M = 0                    # no margin: GNOME draws the rounded corners and shadow
CX, CY = W / 2, 246      # orbit centre
ORBIT = 138              # orbit radius (button centres)
SEG_Y = 36               # segmented control centre
PAGE_NAMES = ["Convert", "Tools"]

# One solid accent (Apple system blue) and Apple-style neutrals. No gradients.
ACCENT = (0.04, 0.52, 1.00)     # #0A84FF
GREEN = (0.20, 0.78, 0.35)      # #34C759
RED = (1.00, 0.27, 0.23)        # #FF453A
THEMES = {
    "light": dict(card=(0.98, 0.98, 0.99, 0.96), edge=(0, 0, 0, 0.08), fill=(0.46, 0.46, 0.50, 0.12),
                  label=(0.11, 0.11, 0.12), secondary=(0.24, 0.24, 0.26, 0.62), seg_on=(1, 1, 1, 1),
                  shadow=0.22, thumb_bg=(0.46, 0.46, 0.50, 0.10)),
    "dark": dict(card=(0.12, 0.12, 0.13, 0.96), edge=(1, 1, 1, 0.10), fill=(0.46, 0.46, 0.50, 0.26),
                 label=(0.96, 0.96, 0.97), secondary=(0.92, 0.92, 0.96, 0.60), seg_on=(0.39, 0.39, 0.40, 1),
                 shadow=0.45, thumb_bg=(1, 1, 1, 0.06)),
}


# Apple-style bubble colours (iOS system palette), laid around the orbit as a rainbow.
SPECTRUM = [(1.00, 0.23, 0.19), (1.00, 0.58, 0.00), (1.00, 0.80, 0.00), (0.20, 0.78, 0.35),
            (0.00, 0.78, 0.75), (0.19, 0.69, 0.78), (0.20, 0.68, 0.90), (0.00, 0.48, 1.00),
            (0.35, 0.34, 0.84), (0.69, 0.32, 0.87), (1.00, 0.18, 0.33)]


def bubble_color(i, n):
    """Evenly sample the spectrum so any number of bubbles forms a smooth rainbow."""
    pos = (i / max(n, 1)) * (len(SPECTRUM) - 1)
    a, f = int(pos), pos - int(pos)
    c0, c1 = SPECTRUM[a], SPECTRUM[min(a + 1, len(SPECTRUM) - 1)]
    return tuple(c0[k] + (c1[k] - c0[k]) * f for k in range(3))


def _ease(t):
    return 1 - (1 - t) ** 3


def _rounded(cr, x, y, w, h, r):
    r = min(r, w / 2, h / 2)
    cr.new_sub_path()
    cr.arc(x + w - r, y + r, r, -math.pi / 2, 0)
    cr.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
    cr.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
    cr.arc(x + r, y + r, r, math.pi, 3 * math.pi / 2)
    cr.close_path()


class RingWindow(Gtk.Window):
    def __init__(self, app, files: list[Path] | None = None, progress_only=False):
        # A compact card-sized window. The title lets the GNOME Shell extension find it.
        super().__init__(application=app, resizable=False, title="Orbit Panel",
                         default_width=W, default_height=H)
        # An empty titlebar gives a borderless window that still gets GNOME's native
        # rounded corners and shadow, so there's no dark layer behind the card.
        self.set_titlebar(Gtk.Box(visible=False))
        self.app = app
        self.add_css_class("orbit-card")
        self.files: list[Path] = []
        self.click_mode = bool(files)
        self.pages: list[list[Action]] = []
        self.page = 0
        self.hover = None              # ("btn", i) | ("seg", i) | ("close",) | ("show",) | None
        self.origin = (0, 0)           # the card fills the window
        self.pointer = None            # pointer position in card coordinates
        self.auto_center = bool(files) or progress_only
        self.scales = {}               # button index -> current scale (hover animation)
        self.appear = 0.0
        self.flip = 1.0
        self.mode = "menu"             # menu | progress | done | error
        self.morph = 0.0
        self.target = self.shown = 0.0
        self.reported = False
        self.job_label = self.result_text = ""
        self.outputs: list[Path] = []
        self.fade = 1.0
        self.thumb = None
        self._t0 = 0.0
        self._seg_timer = None
        self._close_timer = None
        self._entered = self._over = False
        self._ticking = False
        self._icons = {}
        self.theme = THEMES["light"]  # Orbit is always light

        self.area = Gtk.DrawingArea(content_width=W, content_height=H)
        self.area.set_draw_func(self._draw)
        self.set_child(self.area)

        motion = Gtk.EventControllerMotion()
        motion.connect("motion", lambda _c, x, y: self._hover_at(*self._local(x, y)))
        motion.connect("leave", lambda *_: self._hover_at(-999, -999))
        self.area.add_controller(motion)
        click = Gtk.GestureClick()
        click.connect("released", self._on_click)
        self.area.add_controller(click)
        keys = Gtk.EventControllerKey()
        keys.connect("key-pressed", self._on_key)
        self.add_controller(keys)
        if not progress_only:
            drop = Gtk.DropTarget.new(Gdk.FileList, Gdk.DragAction.COPY)
            drop.set_preload(True)
            drop.connect("enter", self._on_enter)
            drop.connect("motion", self._on_motion)
            drop.connect("leave", self._on_leave)
            drop.connect("drop", self._on_drop)
            drop.connect("notify::value", self._on_value)
            self.area.add_controller(drop)
        if files:
            self._set_files(files)

    # ---- lifecycle ----------------------------------------------------------------

    def show_ring(self, timeout_s=None):
        self.present()
        sounds.play("open")
        self._tick()
        # Nothing dragged onto the card? Get out of the way.
        ms = timeout_s * 1000 if timeout_s else (30000 if self.click_mode else 8000)
        self._close_timer = GLib.timeout_add(ms, self._timeout)

    def _timeout(self):
        self._close_timer = None
        if not self._entered and not self.click_mode and self.mode == "menu":
            self.close()
        return False

    def _local(self, x, y):
        """Window coordinates -> card coordinates."""
        if not self.origin:
            return -999, -999
        return x - self.origin[0], y - self.origin[1]

    def released(self):
        """Mouse button / finger went up. If the drag isn't over the card, it ended elsewhere."""
        GLib.timeout_add(700, lambda: (self._close_if_idle(), False)[1])

    def _close_if_idle(self):
        if not self._over and not self.click_mode and self.mode == "menu":
            self.close()

    def next_page(self):
        if len(self.pages) > 1 and self.mode == "menu":
            self._go_page((self.page + 1) % len(self.pages))

    def _go_page(self, n):
        if n != self.page:
            sounds.play("switch")
            self.page = n
            self.flip = 0.0
            self.scales.clear()
            self._tick()

    def _set_files(self, files):
        if files == self.files:
            return
        self.files = files
        self.pages = pages_for(files)
        self.page = 0
        self.thumb = None
        first = files[0]

        def load():
            surf = thumbnail(first)
            GLib.idle_add(lambda: (setattr(self, "thumb", surf), self.area.queue_draw(), False)[2])
        threading.Thread(target=load, daemon=True).start()
        self.area.queue_draw()

    # ---- animation ----------------------------------------------------------------

    def _tick(self):
        if not self._ticking:
            self._ticking = True
            self.add_tick_callback(self._animate)

    def _animate(self, *_):
        busy = False
        if self.appear < 1:
            self.appear = min(1.0, self.appear + 1 / 10)
            busy = True
        if self.flip < 1:
            self.flip = min(1.0, self.flip + 1 / 9)
            busy = True
        for i in range(len(self.actions)):
            want = self._magnify(i)
            cur = self.scales.get(i, 1.0)
            if abs(want - cur) > 0.002:
                self.scales[i] = cur + (want - cur) * 0.3
                busy = True
        if self.mode != "menu":
            if self.morph < 1:
                self.morph = min(1.0, self.morph + 1 / 12)
            if self.mode == "progress" and not self.reported:
                # No numbers from the job yet: creep towards 90% so it never looks frozen.
                elapsed = time.monotonic() - self._t0
                self.target = max(self.target, 0.9 * (1 - math.exp(-elapsed / 3.0)))
            if abs(self.target - self.shown) > 0.001 or self.mode == "progress":
                self.shown += (self.target - self.shown) * 0.18
                busy = True
            busy = busy or self.morph < 1
        self.area.queue_draw()
        if not busy:
            self._ticking = False
        return busy

    # ---- progress -----------------------------------------------------------------

    def start_progress(self, label: str):
        self.mode = "progress"
        sounds.play("start")
        self.job_label = label
        self.target = self.shown = 0.0
        self._t0 = time.monotonic()
        self._tick()

    def set_progress(self, fraction: float):
        self.reported = True
        self.target = max(self.target, fraction)
        self._tick()

    def finish(self, ok: bool, text: str, outputs=()):
        self.mode = "done" if ok else "error"
        sounds.play("success" if ok else "error")
        self.result_text = text
        self.outputs = list(outputs)
        if ok:
            self.target = 1.0
        self._tick()
        GLib.timeout_add(900 if ok else 3000, self._fade_out)

    def _fade_out(self):
        def step():
            self.fade -= 0.08
            self.area.queue_draw()
            if self.fade <= 0:
                self.close()
                return False
            return True
        GLib.timeout_add(16, step)
        return False

    # ---- layout / hit testing -----------------------------------------------------

    @property
    def actions(self) -> list[Action]:
        return self.pages[self.page] if self.pages else []

    def _btn_radius(self):
        return 30 if len(self.actions) <= 8 else 27

    def _btn_pos(self, i):
        n = max(len(self.actions), 1)
        a = -math.pi / 2 + i * 2 * math.pi / n
        return CX + ORBIT * math.cos(a), CY + ORBIT * math.sin(a)

    def _seg_rects(self):
        n = len(self.pages)
        w = 104
        x0 = CX - n * w / 2
        return [(x0 + i * w, SEG_Y - 15, w, 30) for i in range(n)]

    def _hit(self, x, y):
        if math.hypot(x - (M + 22), y - (M + 22)) <= 9:
            return ("close",)
        if self.mode != "menu":
            return None
        if len(self.pages) > 1:
            for i, (sx, sy, sw, sh) in enumerate(self._seg_rects()):
                if sx <= x <= sx + sw and sy <= y <= sy + sh:
                    return ("seg", i)
        r = self._btn_radius() + 8
        for i in range(len(self.actions)):
            bx, by = self._btn_pos(i)
            if math.hypot(x - bx, y - by) <= r:
                return ("btn", i)
        return None

    def _magnify(self, i):
        """Apple Watch style: bubbles near the pointer grow."""
        if not self.pointer or self.mode != "menu":
            return 1.0
        bx, by = self._btn_pos(i)
        d = math.hypot(self.pointer[0] - bx, self.pointer[1] - by)
        return 1.0 + 0.24 * math.exp(-(d / 62) ** 2)

    def _hover_btn(self):
        return self.hover[1] if self.hover and self.hover[0] == "btn" else None

    def _hover_at(self, x, y):
        self.pointer = (x, y) if x > -900 else None
        self._tick()  # bubbles magnify as the pointer moves
        hit = self._hit(x, y)
        if hit == self.hover:
            return
        if hit and hit[0] == "btn":
            sounds.play("hover")
        self.hover = hit
        if self._seg_timer:
            GLib.source_remove(self._seg_timer)
            self._seg_timer = None
        if hit and hit[0] == "seg":  # resting on a segment switches to it, even mid-drag
            self._seg_timer = GLib.timeout_add(250, lambda: (self._go_page(hit[1]), False)[1])
        self._tick()

    # ---- input --------------------------------------------------------------------

    def _files_from(self, value):
        return real_paths([f.get_path() for f in value.get_files() if f.get_path()])

    def _on_enter(self, _t, x, y):
        log.info("drag entered the panel")
        self._entered = self._over = True
        return Gdk.DragAction.COPY

    def _on_value(self, target, _pspec):
        value = target.get_value()
        if value is not None:
            files = self._files_from(value)
            if files:
                self._set_files(files)

    def _on_motion(self, _t, x, y):
        self._over = True
        self._hover_at(*self._local(x, y))
        return Gdk.DragAction.COPY

    def _on_leave(self, _t):
        self._over = False
        self._hover_at(-999, -999)

    def _on_drop(self, _t, value, x, y):
        self._over = False
        self._set_files(self._files_from(value) or self.files)
        hit = self._hit(*self._local(x, y))
        if hit and hit[0] == "btn" and hit[1] < len(self.actions):
            self._choose(self.actions[hit[1]])
        elif hit and hit[0] == "seg":
            self._go_page(hit[1])
            return False
        else:
            return False  # dropped on empty space: keep the card open
        return True

    def _on_click(self, _g, _n, x, y):
        hit = self._hit(*self._local(x, y))
        if not hit:
            return
        if hit[0] == "close":
            self.close()
        elif hit[0] == "seg":
            self._go_page(hit[1])
        elif hit[0] == "btn" and self.files:
            self._choose(self.actions[hit[1]])

    def _on_key(self, _c, keyval, *_):
        if keyval == Gdk.KEY_Escape:
            self.close()
        elif keyval in (Gdk.KEY_Shift_L, Gdk.KEY_Shift_R, Gdk.KEY_Tab):
            self.next_page()
        return True

    def _choose(self, action: Action):
        files = list(self.files)
        if action.dialog:
            self.close()
        self.app.perform(action, files, ring=None if action.dialog else self)

    def do_close_request(self):
        for src in (self._seg_timer, self._close_timer):
            if src:
                GLib.source_remove(src)
        self._seg_timer = self._close_timer = None
        return False

    # ---- drawing ------------------------------------------------------------------

    def _draw(self, _a, cr: cairo.Context, w, h):
        t = self.theme
        a = _ease(self.appear) * max(0.0, self.fade)
        cr.push_group()

        self._close_dot(cr)
        menu_alpha = 1 - _ease(self.morph)
        if menu_alpha > 0.01:
            cr.push_group()
            self._draw_menu(cr)
            cr.pop_group_to_source()
            cr.paint_with_alpha(menu_alpha)
        self._draw_centre(cr)
        if self.mode != "menu":
            cr.push_group()
            self._draw_status(cr)
            cr.pop_group_to_source()
            cr.paint_with_alpha(_ease(self.morph))

        cr.pop_group_to_source()
        cr.paint_with_alpha(a)

    def _close_dot(self, cr):
        x, y = M + 22, M + 22
        cr.new_path()
        cr.arc(x, y, 6.5, 0, 2 * math.pi)
        cr.set_source_rgb(1.0, 0.37, 0.34)
        cr.fill()
        if self.hover == ("close",):
            cr.set_source_rgba(0.35, 0.05, 0.03, 0.8)
            cr.set_line_width(1.4)
            for d in ((-2.5, -2.5, 2.5, 2.5), (2.5, -2.5, -2.5, 2.5)):
                cr.move_to(x + d[0], y + d[1])
                cr.line_to(x + d[2], y + d[3])
            cr.stroke()

    def _draw_menu(self, cr):
        t = self.theme
        # iOS segmented control.
        if len(self.pages) > 1:
            rects = self._seg_rects()
            x0, y0 = rects[0][0], rects[0][1]
            _rounded(cr, x0 - 2, y0 - 2, sum(r[2] for r in rects) + 4, 34, 10)
            cr.set_source_rgba(*t["fill"])
            cr.fill()
            sx, sy, sw, sh = rects[self.page]
            _rounded(cr, sx + 1, sy + 1, sw - 2, sh - 2, 8)
            cr.set_source_rgba(0, 0, 0, 0.10)
            cr.fill()
            _rounded(cr, sx + 1, sy, sw - 2, sh - 2, 8)
            cr.set_source_rgba(*t["seg_on"])
            cr.fill()
            for i, (rx, ry, rw, rh) in enumerate(rects):
                self._text(cr, PAGE_NAMES[i], rx + rw / 2, SEG_Y, t["label"], 10, bold=(i == self.page))
        else:
            self._text(cr, "Orbit", CX, SEG_Y, t["label"], 11, bold=True)

        # Buttons on the orbit (they swing in when the page changes).
        spin = (1 - _ease(self.flip)) * 0.5
        cr.save()
        cr.translate(CX, CY)
        cr.rotate(-spin)
        cr.translate(-CX, -CY)
        alpha = 0.3 + 0.7 * _ease(self.flip)
        for i, act in enumerate(self.actions):
            cr.push_group()
            self._button(cr, i, act)
            cr.pop_group_to_source()
            cr.paint_with_alpha(alpha)
        cr.restore()

        # Explanation line.
        hb = self._hover_btn()
        if hb is not None and hb < len(self.actions):
            act = self.actions[hb]
            self._text(cr, act.label, CX, H - M - 58, t["label"], 11.5, bold=True)
            self._text(cr, act.hint, CX, H - M - 36, t["secondary"], 9.5, width=W - 2 * M - 40)
        elif self.files and len(self.pages) > 1:
            other = PAGE_NAMES[(self.page + 1) % 2]
            self._text(cr, f"Shift for {other}", CX, H - M - 40, t["secondary"], 9.5)
        elif not self.files:
            self._text(cr, "Drop a file here", CX, H - M - 40, t["secondary"], 9.5)

    def _button(self, cr, i, act):
        """A glossy Apple-style bubble: colour gradient, soft shadow, specular highlight."""
        t = self.theme
        x, y = self._btn_pos(i)
        r = self._btn_radius() * self.scales.get(i, 1.0)
        hot = self._hover_btn() == i
        c = bubble_color(i, len(self.actions))
        light = tuple(min(1, v + (1 - v) * 0.35) for v in c)
        deep = tuple(v * 0.78 for v in c)

        cr.new_path()  # shadow / glow
        sh = cairo.RadialGradient(x, y + r * 0.35, r * 0.5, x, y + r * 0.35, r * 1.35)
        sh.add_color_stop_rgba(0, 0, 0, 0, 0.22)
        sh.add_color_stop_rgba(1, 0, 0, 0, 0)
        cr.arc(x, y + r * 0.35, r * 1.35, 0, 2 * math.pi)
        cr.set_source(sh)
        cr.fill()

        body = cairo.RadialGradient(x - r * 0.3, y - r * 0.45, r * 0.1, x, y, r * 1.05)
        body.add_color_stop_rgb(0, *light)
        body.add_color_stop_rgb(0.55, *c)
        body.add_color_stop_rgb(1, *deep)
        cr.arc(x, y, r, 0, 2 * math.pi)
        cr.set_source(body)
        cr.fill()

        cr.save()  # specular highlight: a soft glossy cap
        cr.translate(x, y - r * 0.42)
        cr.scale(r * 0.62, r * 0.36)
        gloss = cairo.LinearGradient(0, -1, 0, 1)
        gloss.add_color_stop_rgba(0, 1, 1, 1, 0.55)
        gloss.add_color_stop_rgba(1, 1, 1, 1, 0.0)
        cr.arc(0, 0, 1, 0, 2 * math.pi)
        cr.set_source(gloss)
        cr.fill()
        cr.restore()

        cr.arc(x, y, r - 0.5, 0, 2 * math.pi)  # crisp rim
        cr.set_source_rgba(1, 1, 1, 0.9 if hot else 0.25)
        cr.set_line_width(2 if hot else 1)
        cr.stroke()

        # Light bubbles (yellow) get dark ink so labels stay readable.
        lum = 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]
        ink = (0.25, 0.18, 0.0) if lum > 0.68 else (1, 1, 1)
        if act.icon and self._paint_icon(cr, act.icon, x - 10, y - 10, ink):
            self._text(cr, act.label, x, y + r + 12, t["label"], 8.5, bold=hot)
        else:
            size = (10.5 if len(act.label) <= 4 else 8.5) * min(1.12, self.scales.get(i, 1.0))
            self._text(cr, act.label, x, y + 0.5, (0, 0, 0, 0.18), size, bold=True)  # soft text shadow
            self._text(cr, act.label, x, y - 0.5, ink, size, bold=True)

    def _draw_centre(self, cr):
        """File preview, or the progress ring around it."""
        t = self.theme
        busy = self.mode != "menu"
        tw = 92
        tx, ty = CX - tw / 2, CY - tw / 2 - (14 if not busy else 0)
        _rounded(cr, tx, ty, tw, tw, 20)
        cr.set_source_rgba(*t["thumb_bg"])
        cr.fill()
        if self.thumb:
            sw, sh = self.thumb.get_width(), self.thumb.get_height()
            k = min((tw - 12) / sw, (tw - 12) / sh)
            cr.save()
            _rounded(cr, tx, ty, tw, tw, 20)
            cr.clip()
            cr.translate(CX - sw * k / 2, ty + tw / 2 - sh * k / 2)
            cr.scale(k, k)
            cr.set_source_surface(self.thumb, 0, 0)
            cr.paint()
            cr.restore()
        elif self.files:
            ext = self.files[0].suffix.lstrip(".").upper()[:4] or "FILE"
            self._paint_icon(cr, "text-x-generic-symbolic", CX - 16, ty + 18, t["secondary"][:3], 32)
            self._text(cr, ext, CX, ty + tw - 22, t["secondary"][:3], 10, bold=True)
        else:
            self._paint_icon(cr, "go-down-symbolic", CX - 16, ty + tw / 2 - 16, t["secondary"][:3], 32)

        if not busy and self.files:
            name = self.files[0].name if len(self.files) == 1 else f"{len(self.files)} files"
            self._text(cr, name, CX, ty + tw + 16, t["label"], 9.5, bold=True, width=150)
            self._text(cr, self._size_text(), CX, ty + tw + 32, t["secondary"], 8.5)

        if busy:  # progress ring hugging the preview
            pr = 64
            k = _ease(self.morph)
            cr.set_line_width(4)
            cr.set_line_cap(cairo.LINE_CAP_ROUND)
            cr.new_path()
            cr.arc(CX, CY, pr, 0, 2 * math.pi)
            cr.set_source_rgba(*t["fill"][:3], t["fill"][3] * k)
            cr.stroke()
            frac = min(1.0, self.shown)
            if frac > 0.003 or self.mode == "error":
                cr.new_path()
                cr.arc(CX, CY, pr, -math.pi / 2, -math.pi / 2 + 2 * math.pi * (1 if self.mode == "error" else frac))
                if self.mode == "error":
                    cr.set_source_rgb(*RED)
                elif self.mode == "done" and frac > 0.99:
                    cr.set_source_rgb(*GREEN)
                else:
                    cr.set_source_rgb(*ACCENT)
                cr.stroke()
            if self.mode in ("done", "error") and (frac > 0.99 or self.mode == "error"):
                self._badge(cr, CX + 44, CY + 44, ok=self.mode == "done")

    def _badge(self, cr, x, y, ok):
        cr.new_path()
        cr.arc(x, y, 15, 0, 2 * math.pi)
        cr.set_source_rgba(*self.theme["card"][:3], 1)
        cr.fill()
        cr.arc(x, y, 12, 0, 2 * math.pi)
        cr.set_source_rgb(*(GREEN if ok else RED))
        cr.fill()
        cr.set_source_rgb(1, 1, 1)
        cr.set_line_width(2.6)
        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        if ok:
            cr.move_to(x - 5, y)
            cr.line_to(x - 1.5, y + 4)
            cr.line_to(x + 5.5, y - 4)
        else:
            cr.move_to(x - 4, y - 4)
            cr.line_to(x + 4, y + 4)
            cr.move_to(x + 4, y - 4)
            cr.line_to(x - 4, y + 4)
        cr.stroke()

    def _draw_status(self, cr):
        t = self.theme
        if self.mode == "progress":
            self._text(cr, self.job_label, CX, SEG_Y, t["label"], 12, bold=True)
            self._text(cr, f"{int(min(1, self.shown) * 100)}%", CX, CY + 98, t["secondary"], 13)
        elif self.mode == "done":
            self._text(cr, self.result_text, CX, CY + 98, t["label"], 10.5, bold=True, width=W - 2 * M - 40)
        else:
            self._text(cr, self.result_text, CX, CY + 100, t["secondary"], 9.5, width=W - 2 * M - 40)

    # ---- helpers ------------------------------------------------------------------

    def _size_text(self):
        try:
            size = sum(p.stat().st_size for p in self.files)
        except OSError:
            return ""
        for unit in ("B", "KB", "MB", "GB"):
            if size < 1024 or unit == "GB":
                return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
            size /= 1024

    def _text(self, cr, text, x, y, rgb, size=10, bold=False, width=None):
        if not text:
            return
        layout = PangoCairo.create_layout(cr)
        font = Pango.FontDescription.from_string(
            f"Geist, Cantarell, Sans {'Semi-Bold' if bold else 'Medium'} {size}")
        layout.set_font_description(font)
        if width:
            layout.set_width(int(width * Pango.SCALE))
            layout.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
            layout.set_alignment(Pango.Alignment.CENTER)
        layout.set_text(text, -1)
        tw, th = layout.get_pixel_size()
        lx = x - (width / 2 if width else tw / 2)
        cr.move_to(lx, y - th / 2)
        cr.set_source_rgba(*rgb) if len(rgb) == 4 else cr.set_source_rgb(*rgb)
        PangoCairo.show_layout(cr, layout)
        cr.new_path()

    def _paint_icon(self, cr, name, x, y, rgb, size=20):
        """Draw a symbolic theme icon tinted with rgb. Returns False if missing."""
        key = (name, size)
        if key not in self._icons:
            pix = None
            try:
                theme = Gtk.IconTheme.get_for_display(self.get_display())
                if theme.has_icon(name):
                    f = theme.lookup_icon(name, None, size, 1, Gtk.TextDirection.NONE, 0).get_file()
                    if f and f.get_path():
                        pix = GdkPixbuf.Pixbuf.new_from_file_at_size(f.get_path(), size, size)
            except GLib.Error:
                pix = None
            self._icons[key] = pix
        pix = self._icons[key]
        if not pix:
            return False
        cr.save()
        Gdk.cairo_set_source_pixbuf(cr, pix, x, y)
        mask = cr.get_source()
        cr.set_source_rgb(*rgb[:3])
        cr.mask(mask)
        cr.restore()
        cr.new_path()
        return True
