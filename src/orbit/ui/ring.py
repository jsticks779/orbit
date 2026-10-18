"""The ring: a transparent fullscreen overlay with a radial menu.

Two ways in:
  * drop mode  - summoned by drag + Shift; the ring appears where the drag
                 enters, the file is dropped on a slice.
  * click mode - opened for known files (`orbit ring FILE`, Files menu);
                 the ring sits in the middle and slices are clicked.
"""

import math
from pathlib import Path

import cairo
import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("PangoCairo", "1.0")
from gi.repository import Gdk, GLib, Gtk, Pango, PangoCairo  # noqa: E402

from ..core.actions import Action, pages_for  # noqa: E402

R_OUT, R_IN, R_HUB = 190, 78, 62      # outer edge, inner edge, centre hub
GAP = 7                               # space between slices (px)
DWELL_MS = 650                        # hover the hub this long to flip page
PAGE_NAMES = ["Convert", "Tools"]

# Warm, glassy palette like the macOS original.
GLASS = (1.0, 0.94, 0.90, 0.30)
GLASS_EDGE = (1.0, 1.0, 1.0, 0.55)
SLICE = (0.99, 0.86, 0.77, 0.94)
SLICE_HOT = (0.91, 0.29, 0.18, 0.97)
INK = (0.36, 0.20, 0.12)
INK_HOT = (1.0, 1.0, 1.0)


def _ease(t):
    return 1 - (1 - t) ** 3


class RingWindow(Gtk.Window):
    def __init__(self, app, files: list[Path] | None = None):
        super().__init__(application=app, decorated=False, title="Orbit")
        self.app = app
        self.add_css_class("orbit-overlay")
        self.files: list[Path] = list(files or [])
        self.click_mode = bool(files)
        self.pages: list[list[Action]] = pages_for(self.files) if self.files else []
        self.page = 0
        self.center = None            # (x, y) once placed
        self.hover = None             # slice index, "hub" or None
        self.appear = 0.0             # 0..1 entrance animation
        self.flip = 1.0               # 0..1 page-change animation
        self._dwell = None
        self._close_timer = None
        self._entered = False

        self.area = Gtk.DrawingArea(hexpand=True, vexpand=True)
        self.area.set_draw_func(self._draw)
        self.set_child(self.area)

        drop = Gtk.DropTarget.new(Gdk.FileList, Gdk.DragAction.COPY)
        drop.set_preload(True)
        drop.connect("enter", self._on_enter)
        drop.connect("motion", self._on_motion)
        drop.connect("leave", self._on_leave)
        drop.connect("drop", self._on_drop)
        drop.connect("notify::value", self._on_value)
        self.area.add_controller(drop)

        motion = Gtk.EventControllerMotion()
        motion.connect("motion", lambda _c, x, y: self._hover_at(x, y) if self.click_mode else None)
        self.area.add_controller(motion)
        click = Gtk.GestureClick()
        click.connect("released", self._on_click)
        self.area.add_controller(click)
        keys = Gtk.EventControllerKey()
        keys.connect("key-pressed", self._on_key)
        self.add_controller(keys)

        self.fullscreen()

    # ---- lifecycle ----------------------------------------------------------

    def show_ring(self, timeout_s=8):
        self.present()
        if self.click_mode:
            GLib.idle_add(self._place_middle)
        # Nothing dragged in? Get out of the way.
        self._close_timer = GLib.timeout_add_seconds(timeout_s, self._timeout)

    def _timeout(self):
        self._close_timer = None
        if not self._entered and not self.click_mode:
            self.close()
        return False

    def _place_middle(self):
        self._place(self.get_width() / 2, self.get_height() / 2)
        return False

    def _place(self, x, y):
        if self.center:
            return
        w, h = max(self.get_width(), 2 * R_OUT), max(self.get_height(), 2 * R_OUT)
        m = R_OUT + 24
        self.center = (min(max(x, m), w - m), min(max(y, m), h - m))
        self.appear = 0.0
        self.add_tick_callback(self._animate)

    def _animate(self, _widget, clock):
        done = True
        step = 1 / 9
        if self.appear < 1:
            self.appear = min(1.0, self.appear + step)
            done = False
        if self.flip < 1:
            self.flip = min(1.0, self.flip + step)
            done = False
        self.area.queue_draw()
        return not done

    def released(self):
        """Mouse button went up (from the gesture watcher). If nothing was dropped, close."""
        GLib.timeout_add(350, lambda: (self.close() if not self.click_mode else None, False)[1])

    def next_page(self):
        if len(self.pages) > 1:
            self.page = (self.page + 1) % len(self.pages)
            self.flip = 0.0
            self.add_tick_callback(self._animate)

    # ---- geometry -------------------------------------------------------------

    @property
    def actions(self) -> list[Action]:
        return self.pages[self.page] if self.pages else []

    def _hit(self, x, y):
        if not self.center:
            return None
        dx, dy = x - self.center[0], y - self.center[1]
        r = math.hypot(dx, dy)
        if r <= R_HUB:
            return "hub"
        if not (R_IN <= r <= R_OUT + 20) or not self.actions:
            return None
        n = len(self.actions)
        ang = (math.atan2(dy, dx) + math.pi / 2 + math.pi / n) % (2 * math.pi)
        return int(ang / (2 * math.pi / n)) % n

    def _hover_at(self, x, y):
        hit = self._hit(x, y)
        if hit != self.hover:
            self.hover = hit
            if self._dwell:
                GLib.source_remove(self._dwell)
                self._dwell = None
            if hit == "hub" and len(self.pages) > 1:
                self._dwell = GLib.timeout_add(DWELL_MS, self._dwell_flip)
            self.area.queue_draw()

    def _dwell_flip(self):
        self._dwell = None
        self.next_page()
        return False

    # ---- drag and drop --------------------------------------------------------

    def _on_enter(self, _t, x, y):
        self._entered = True
        self._place(x, y)
        return Gdk.DragAction.COPY

    def _on_value(self, target, _pspec):
        value = target.get_value()
        if value is None:
            return
        files = [Path(f.get_path()) for f in value.get_files() if f.get_path()]
        if files and files != self.files:
            self.files = files
            self.pages = pages_for(files)
            self.page = 0
            self.area.queue_draw()

    def _on_motion(self, _t, x, y):
        self._hover_at(x, y)
        return Gdk.DragAction.COPY

    def _on_leave(self, _t):
        self.hover = None
        self.area.queue_draw()

    def _on_drop(self, _t, value, x, y):
        files = [Path(f.get_path()) for f in value.get_files() if f.get_path()]
        self.files = files or self.files
        if not self.pages:
            self.pages = pages_for(self.files)
        hit = self._hit(x, y)
        if isinstance(hit, int) and hit < len(self.actions):
            self._choose(self.actions[hit])
        else:
            self.close()
        return True

    def _on_click(self, _g, _n, x, y):
        hit = self._hit(x, y)
        if hit == "hub":
            self.next_page()
        elif isinstance(hit, int) and hit < len(self.actions):
            self._choose(self.actions[hit])
        else:
            self.close()

    def _on_key(self, _c, keyval, *_):
        if keyval == Gdk.KEY_Escape:
            self.close()
        elif keyval in (Gdk.KEY_Shift_L, Gdk.KEY_Shift_R, Gdk.KEY_Tab):
            self.next_page()
        return True

    def _choose(self, action: Action):
        files = list(self.files)
        self.close()
        self.app.perform(action, files)

    def do_close_request(self):
        for src in (self._dwell, self._close_timer):
            if src:
                GLib.source_remove(src)
        self._dwell = self._close_timer = None
        return False

    # ---- drawing --------------------------------------------------------------

    def _draw(self, _area, cr: cairo.Context, w, h):
        if not self.center:
            return
        cx, cy = self.center
        s = 0.6 + 0.4 * _ease(self.appear)
        cr.save()
        cr.translate(cx, cy)
        cr.scale(s, s)
        cr.push_group()

        # Glass disc behind the slices.
        cr.arc(0, 0, R_OUT + 14, 0, 2 * math.pi)
        cr.set_source_rgba(*GLASS)
        cr.fill_preserve()
        cr.set_source_rgba(*GLASS_EDGE)
        cr.set_line_width(1.5)
        cr.stroke()

        acts = self.actions
        n = max(len(acts), 1)
        spin = (1 - _ease(self.flip)) * (math.pi / 3)
        for i, act in enumerate(acts):
            mid = -math.pi / 2 + i * 2 * math.pi / n - spin
            self._slice(cr, mid, 2 * math.pi / n, act, hot=(self.hover == i))

        self._hub(cr)
        if len(self.pages) > 1:
            self._dots(cr)

        cr.pop_group_to_source()
        cr.paint_with_alpha(_ease(self.appear) * (0.4 + 0.6 * _ease(self.flip)))
        cr.restore()

    def _slice(self, cr, mid, span, act, hot):
        a0, a1 = mid - span / 2, mid + span / 2
        # Inset by half the gap plus half the rounding stroke so gaps stay visible.
        full = span >= 2 * math.pi - 0.01
        r_out, r_in = R_OUT - 5, R_IN + 5
        inset_o = 0 if full else (GAP / 2 + 5) / r_out
        inset_i = 0 if full else (GAP / 2 + 5) / r_in
        cr.new_path()
        cr.arc(0, 0, r_out, a0 + inset_o, a1 - inset_o)
        cr.arc_negative(0, 0, r_in, a1 - inset_i, a0 + inset_i)
        cr.close_path()
        cr.set_source_rgba(*(SLICE_HOT if hot else SLICE))
        cr.set_line_join(cairo.LINE_JOIN_ROUND)
        cr.set_line_width(10)  # thick round stroke = soft rounded corners
        cr.fill_preserve()
        cr.stroke()

        rm = (R_OUT + R_IN) / 2 + 4
        self._text(cr, act.label.upper(), rm * math.cos(mid), rm * math.sin(mid),
                   INK_HOT if hot else INK, size=10.5 if len(act.label) <= 6 else 9, bold=True)

    def _hub(self, cr):
        hot = self.hover == "hub"
        cr.arc(0, 0, R_HUB, 0, 2 * math.pi)
        cr.set_source_rgba(1, 0.97, 0.94, 0.97 if hot else 0.9)
        cr.fill()
        if isinstance(self.hover, int) and self.hover < len(self.actions):
            self._text(cr, self.actions[self.hover].label, 0, -4, INK, size=12, bold=True)
            self._text(cr, self._size_text(), 0, 14, INK, size=8.5)
        elif self.files:
            name = self.files[0].name if len(self.files) == 1 else f"{len(self.files)} files"
            self._text(cr, name if len(name) < 16 else name[:14] + "…", 0, -6, INK, size=9.5, bold=True)
            hint = PAGE_NAMES[self.page] + ("  ⇧" if len(self.pages) > 1 else "")
            self._text(cr, hint, 0, 12, INK, size=8.5)
        else:
            self._text(cr, "Orbit", 0, 0, INK, size=12, bold=True)

    def _size_text(self):
        try:
            size = sum(p.stat().st_size for p in self.files)
        except OSError:
            return ""
        for unit in ("B", "KB", "MB", "GB"):
            if size < 1024 or unit == "GB":
                return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
            size /= 1024

    def _dots(self, cr):
        n = len(self.pages)
        for i in range(n):
            x = (i - (n - 1) / 2) * 14
            cr.arc(x, R_OUT + 30, 4, 0, 2 * math.pi)
            cr.set_source_rgba(1, 1, 1, 0.95 if i == self.page else 0.45)
            cr.fill()

    def _text(self, cr, text, x, y, rgb, size=10, bold=False):
        layout = PangoCairo.create_layout(cr)
        font = Pango.FontDescription.from_string(f"Inter, Cantarell, Sans {'Bold' if bold else ''} {size}")
        layout.set_font_description(font)
        layout.set_text(text, -1)
        tw, th = layout.get_pixel_size()
        cr.move_to(x - tw / 2, y - th / 2)
        cr.set_source_rgb(*rgb)
        PangoCairo.show_layout(cr, layout)
