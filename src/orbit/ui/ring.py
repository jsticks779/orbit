"""The ring: a transparent fullscreen overlay with a radial menu.

Modes:
  * drop     - summoned by drag + Shift; the ring appears under the cursor
               and the file is dropped on a slice.
  * click    - opened for known files (`orbit ring FILE`, Files menu).
  * progress - after a choice the ring shrinks into a progress circle that
               fills at the real speed of the job, then shows ✓ or ✗.
               The overlay is click-through while it runs.
"""

import logging
import math
import time
from pathlib import Path

import cairo
import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("PangoCairo", "1.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gdk, GdkPixbuf, GLib, Gtk, Pango, PangoCairo  # noqa: E402

from ..core.actions import Action, pages_for  # noqa: E402
from ..core.portal import real_paths  # noqa: E402

log = logging.getLogger("orbit")

R_OUT, R_IN, R_HUB = 190, 80, 64     # outer edge, inner edge, centre hub
RIM = 16                             # glass rim around the slices
GAP = 8                              # space between slices (px)
POP = 7                              # hovered slice moves outward (px)
R_PROG = 54                          # progress circle radius
DWELL_MS = 650                       # hover the hub this long to flip page
PAGE_NAMES = ["Convert", "Tools"]

INK = (0.33, 0.18, 0.10)
WHITE = (1, 1, 1)
HOT_A, HOT_B = (1.0, 0.45, 0.25), (0.86, 0.20, 0.13)     # hovered slice gradient
SLICE_A, SLICE_B = (1.0, 0.93, 0.87), (0.98, 0.80, 0.68)  # normal slice gradient
OK_GREEN = (0.20, 0.72, 0.42)
ERR_RED = (0.88, 0.22, 0.18)


def _ease(t):
    return 1 - (1 - t) ** 3


def _rounded_rect(cr, x, y, w, h, r):
    cr.new_sub_path()
    cr.arc(x + w - r, y + r, r, -math.pi / 2, 0)
    cr.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
    cr.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
    cr.arc(x + r, y + r, r, math.pi, 3 * math.pi / 2)
    cr.close_path()


class RingWindow(Gtk.Window):
    def __init__(self, app, files: list[Path] | None = None, progress_only=False):
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
        self.mode = "menu"            # menu | progress | done | error
        self.morph = 0.0              # 0..1 menu -> progress circle
        self.target = self.shown = 0.0
        self.reported = False
        self.job_label = self.result_text = ""
        self.fade = 1.0
        self._t0 = 0.0
        self._dwell = None
        self._close_timer = None
        self._entered = False
        self._over = False            # a drag is currently hovering the overlay
        self._ticking = False
        self._icons = {}

        self.area = Gtk.DrawingArea(hexpand=True, vexpand=True)
        self.area.set_draw_func(self._draw)
        self.set_child(self.area)

        if not progress_only:
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

    # ---- lifecycle ----------------------------------------------------------------

    def show_ring(self, timeout_s=None):
        self.present()
        if self.click_mode:
            GLib.idle_add(self._place_middle)
        # Shift pressed without a real drag (e.g. finger resting on the touchpad)? Close fast.
        ms = timeout_s * 1000 if timeout_s else (8000 if self.click_mode else 2500)
        self._close_timer = GLib.timeout_add(ms, self._timeout)

    def _timeout(self):
        self._close_timer = None
        if not self._entered and not self.click_mode and self.mode == "menu":
            self.close()
        return False

    def _place_middle(self):
        self._place(self.get_width() / 2, self.get_height() / 2)
        return False

    def _place(self, x, y):
        if self.center:
            return
        w, h = max(self.get_width(), 2 * R_OUT), max(self.get_height(), 2 * R_OUT)
        m = R_OUT + RIM + 12
        self.center = (min(max(x, m), w - m), min(max(y, m), h - m - 70))
        self.appear = 0.0
        self._tick()

    def _tick(self):
        if not self._ticking:
            self._ticking = True
            self.add_tick_callback(self._animate)

    def _animate(self, _widget, _clock):
        busy = False
        step = 1 / 9
        if self.appear < 1:
            self.appear = min(1.0, self.appear + step)
            busy = True
        if self.flip < 1:
            self.flip = min(1.0, self.flip + step)
            busy = True
        if self.mode != "menu":
            if self.morph < 1:
                self.morph = min(1.0, self.morph + 1 / 12)
            if self.mode == "progress" and not self.reported:
                # No numbers from the job yet: creep towards 90% so it never looks frozen.
                elapsed = time.monotonic() - self._t0
                self.target = max(self.target, 0.9 * (1 - math.exp(-elapsed / 3.0)))
            self.shown += (self.target - self.shown) * 0.18
            busy = True
        self.area.queue_draw()
        if not busy:
            self._ticking = False
        return busy

    def released(self):
        """Button/finger went up. Touchpad tap-and-drag lifts the finger mid-drag,
        so only close if no drag is hovering the ring any more."""
        GLib.timeout_add(350, lambda: (self._close_if_idle(), False)[1])

    def _close_if_idle(self):
        if not self._over and not self.click_mode and self.mode == "menu":
            self.close()

    def next_page(self):
        if len(self.pages) > 1 and self.mode == "menu":
            self.page = (self.page + 1) % len(self.pages)
            self.flip = 0.0
            self._tick()

    # ---- progress -----------------------------------------------------------------

    def start_progress(self, label: str):
        """Turn the ring into a progress circle and let clicks pass through."""
        self.mode = "progress"
        self.job_label = label
        self.target = self.shown = 0.0
        self._t0 = time.monotonic()
        if not self.center:
            self._place_middle()
        surface = self.get_surface()
        if surface:
            surface.set_input_region(cairo.Region())
        self._tick()

    def set_progress(self, fraction: float):
        self.reported = True
        self.target = max(self.target, fraction)
        self._tick()

    def finish(self, ok: bool, text: str):
        self.mode = "done" if ok else "error"
        self.result_text = text
        if ok:
            self.target = 1.0
        self._tick()
        GLib.timeout_add(1500 if ok else 3500, self._fade_out)

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

    # ---- geometry -----------------------------------------------------------------

    @property
    def actions(self) -> list[Action]:
        return self.pages[self.page] if self.pages else []

    def _hit(self, x, y):
        if not self.center or self.mode != "menu":
            return None
        dx, dy = x - self.center[0], y - self.center[1]
        r = math.hypot(dx, dy)
        if r <= R_HUB:
            return "hub"
        if not (R_IN - 6 <= r <= R_OUT + RIM + 24) or not self.actions:
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

    # ---- drag and drop ------------------------------------------------------------

    def _files_from(self, value):
        return real_paths([f.get_path() for f in value.get_files() if f.get_path()])

    def _on_enter(self, _t, x, y):
        log.info("drag entered ring at %.0f,%.0f", x, y)
        self._entered = self._over = True
        # GNOME reports (0, 0) when a drag enters a freshly opened window;
        # wait for the first real motion to place the ring under the cursor.
        if x or y:
            self._place(x, y)
        return Gdk.DragAction.COPY

    def _on_value(self, target, _pspec):
        value = target.get_value()
        if value is None:
            return
        files = self._files_from(value)
        if files and files != self.files:
            self.files = files
            self.pages = pages_for(files)
            self.page = 0
            self.area.queue_draw()

    def _on_motion(self, _t, x, y):
        self._over = True
        self._place(x, y)
        self._hover_at(x, y)
        return Gdk.DragAction.COPY

    def _on_leave(self, _t):
        # The overlay covers the screen, so leaving means the drag ended or was cancelled.
        self._over = False
        self.hover = None
        self.area.queue_draw()
        GLib.timeout_add(400, lambda: (self._close_if_idle(), False)[1])

    def _on_drop(self, _t, value, x, y):
        self._over = False
        self.files = self._files_from(value) or self.files
        if not self.pages:
            self.pages = pages_for(self.files)
        hit = self._hit(x, y)
        if isinstance(hit, int) and hit < len(self.actions):
            self._choose(self.actions[hit])
        else:
            self.close()
        return True

    def _on_click(self, _g, _n, x, y):
        if self.mode != "menu":
            return
        hit = self._hit(x, y)
        if hit == "hub":
            self.next_page()
        elif isinstance(hit, int) and hit < len(self.actions):
            self._choose(self.actions[hit])
        else:
            self.close()

    def _on_key(self, _c, keyval, *_):
        if keyval == Gdk.KEY_Escape and self.mode == "menu":
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
        for src in (self._dwell, self._close_timer):
            if src:
                GLib.source_remove(src)
        self._dwell = self._close_timer = None
        return False

    # ---- drawing ------------------------------------------------------------------

    def _draw(self, _area, cr: cairo.Context, w, h):
        if not self.center:
            return
        cx, cy = self.center
        cr.save()
        cr.translate(cx, cy)
        cr.push_group()
        if self.mode == "menu" or self.morph < 1:
            cr.save()
            s = (0.6 + 0.4 * _ease(self.appear)) * (1 - 0.6 * _ease(self.morph))
            cr.scale(s, s)
            cr.push_group()
            self._draw_menu(cr)
            cr.pop_group_to_source()
            cr.paint_with_alpha(_ease(self.appear) * (0.4 + 0.6 * _ease(self.flip)) * (1 - _ease(self.morph)))
            cr.restore()
        if self.mode != "menu":
            cr.push_group()
            self._draw_progress(cr)
            cr.pop_group_to_source()
            cr.paint_with_alpha(_ease(self.morph))
        cr.pop_group_to_source()
        cr.paint_with_alpha(max(0.0, self.fade))
        cr.restore()

    def _draw_menu(self, cr):
        # Soft shadow under the whole ring.
        shadow = cairo.RadialGradient(0, 14, R_OUT * 0.6, 0, 14, R_OUT + RIM + 34)
        shadow.add_color_stop_rgba(0, 0, 0, 0, 0.28)
        shadow.add_color_stop_rgba(1, 0, 0, 0, 0)
        cr.arc(0, 14, R_OUT + RIM + 34, 0, 2 * math.pi)
        cr.set_source(shadow)
        cr.fill()

        # Frosted glass rim: bright at the top, softer below.
        glass = cairo.LinearGradient(0, -R_OUT - RIM, 0, R_OUT + RIM)
        glass.add_color_stop_rgba(0, 1, 1, 1, 0.62)
        glass.add_color_stop_rgba(1, 1, 0.92, 0.86, 0.38)
        cr.arc(0, 0, R_OUT + RIM, 0, 2 * math.pi)
        cr.set_source(glass)
        cr.fill_preserve()
        cr.set_source_rgba(1, 1, 1, 0.8)
        cr.set_line_width(1.2)
        cr.stroke()
        cr.new_path()
        cr.arc(0, 0, R_OUT + RIM - 3, math.pi * 1.15, math.pi * 1.85)  # top highlight
        cr.set_source_rgba(1, 1, 1, 0.75)
        cr.set_line_width(2)
        cr.stroke()

        acts = self.actions
        n = max(len(acts), 1)
        spin = (1 - _ease(self.flip)) * (math.pi / 3)
        for i, act in enumerate(acts):
            mid = -math.pi / 2 + i * 2 * math.pi / n - spin
            self._slice(cr, mid, 2 * math.pi / n, act, hot=(self.hover == i))

        self._hub(cr)
        self._hint(cr)

    def _slice(self, cr, mid, span, act, hot):
        cr.save()
        if hot:
            cr.translate(POP * math.cos(mid), POP * math.sin(mid))
        full = span >= 2 * math.pi - 0.01
        r_out, r_in = R_OUT - 5, R_IN + 5
        inset_o = 0 if full else (GAP / 2 + 5) / r_out
        inset_i = 0 if full else (GAP / 2 + 5) / r_in
        a0, a1 = mid - span / 2, mid + span / 2
        cr.new_path()
        cr.arc(0, 0, r_out, a0 + inset_o, a1 - inset_o)
        cr.arc_negative(0, 0, r_in, a1 - inset_i, a0 + inset_i)
        cr.close_path()
        a, b = (HOT_A, HOT_B) if hot else (SLICE_A, SLICE_B)
        grad = cairo.LinearGradient(0, -R_OUT, 0, R_OUT)
        grad.add_color_stop_rgba(0, *a, 0.97)
        grad.add_color_stop_rgba(1, *b, 0.97)
        cr.set_source(grad)
        cr.set_line_join(cairo.LINE_JOIN_ROUND)
        cr.set_line_width(10)  # thick round stroke = soft rounded corners
        cr.fill_preserve()
        cr.stroke()

        rm = (R_OUT + R_IN) / 2 + 3
        x, y = rm * math.cos(mid), rm * math.sin(mid)
        ink = WHITE if hot else INK
        size = 10.5 if len(act.label) <= 6 else 9
        if act.icon and self._paint_icon(cr, act.icon, x - 10, y - 22, ink):
            self._text(cr, act.label.upper(), x, y + 10, ink, size=8.5, bold=True, spacing=0.6)
        else:
            self._text(cr, act.label.upper(), x, y, ink, size=size, bold=True, spacing=0.6)
        cr.restore()

    def _hub(self, cr):
        hot = self.hover == "hub"
        cr.new_path()  # don't connect to the last text position
        cr.arc(0, 0, R_HUB, 0, 2 * math.pi)
        g = cairo.RadialGradient(0, -20, 4, 0, 0, R_HUB)
        g.add_color_stop_rgba(0, 1, 1, 1, 0.98)
        g.add_color_stop_rgba(1, 1, 0.95, 0.91, 0.92 if hot else 0.85)
        cr.set_source(g)
        cr.fill_preserve()
        cr.set_source_rgba(1, 1, 1, 0.9)
        cr.set_line_width(1.2)
        cr.stroke()
        if isinstance(self.hover, int) and self.hover < len(self.actions):
            self._text(cr, self.actions[self.hover].label, 0, -7, INK, size=12.5, bold=True)
            self._pill(cr, self._size_text(), 0, 15, size=8.5)
        elif self.files:
            name = self.files[0].name if len(self.files) == 1 else f"{len(self.files)} files"
            self._text(cr, name if len(name) < 15 else name[:13] + "…", 0, -7, INK, size=9.5, bold=True)
            self._pill(cr, self._size_text(), 0, 15, size=8.5)
        else:
            self._text(cr, "Orbit", 0, 0, INK, size=13, bold=True)

    def _hint(self, cr):
        """The explanation pill under the ring, plus page dots."""
        y = R_OUT + RIM + 30
        if isinstance(self.hover, int) and self.hover < len(self.actions):
            text = self.actions[self.hover].hint or self.actions[self.hover].label
        elif len(self.pages) > 1:
            other = PAGE_NAMES[(self.page + 1) % len(self.pages)]
            text = f"Tap Shift or rest on the centre for {other}"
        else:
            text = "Drop on a slice"
        self._pill(cr, text, 0, y, size=10, dark=True, pad=14)
        if len(self.pages) > 1:
            for i in range(len(self.pages)):
                x = (i - (len(self.pages) - 1) / 2) * 14
                cr.new_path()
                cr.arc(x, y + 30, 3.5 if i != self.page else 4.5, 0, 2 * math.pi)
                cr.set_source_rgba(1, 1, 1, 0.95 if i == self.page else 0.5)
                cr.fill()

    def _draw_progress(self, cr):
        # Glass disc with a track and a glowing arc.
        shadow = cairo.RadialGradient(0, 8, R_PROG * 0.6, 0, 8, R_PROG + 28)
        shadow.add_color_stop_rgba(0, 0, 0, 0, 0.3)
        shadow.add_color_stop_rgba(1, 0, 0, 0, 0)
        cr.arc(0, 8, R_PROG + 28, 0, 2 * math.pi)
        cr.set_source(shadow)
        cr.fill()
        cr.arc(0, 0, R_PROG + 10, 0, 2 * math.pi)
        g = cairo.LinearGradient(0, -R_PROG, 0, R_PROG)
        g.add_color_stop_rgba(0, 1, 1, 1, 0.95)
        g.add_color_stop_rgba(1, 1, 0.93, 0.88, 0.9)
        cr.set_source(g)
        cr.fill()

        cr.set_line_width(8)
        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        cr.arc(0, 0, R_PROG - 4, 0, 2 * math.pi)
        cr.set_source_rgba(0.95, 0.80, 0.70, 0.6)
        cr.stroke()
        frac = min(1.0, self.shown)
        finished = self.mode == "done" and frac > 0.99
        if frac > 0.002 or self.mode == "error":
            end = -math.pi / 2 + 2 * math.pi * (1.0 if self.mode == "error" else frac)
            cr.arc(0, 0, R_PROG - 4, -math.pi / 2, end)
            if finished or self.mode == "error":
                cr.set_source_rgb(*(OK_GREEN if finished else ERR_RED))
            else:
                arc = cairo.LinearGradient(-R_PROG, -R_PROG, R_PROG, R_PROG)
                arc.add_color_stop_rgb(0, *HOT_A)
                arc.add_color_stop_rgb(1, *HOT_B)
                cr.set_source(arc)
            cr.stroke()

        cr.set_line_width(6)
        if finished:
            cr.move_to(-16, 1)
            cr.line_to(-5, 12)
            cr.line_to(17, -12)
            cr.set_source_rgb(*OK_GREEN)
            cr.stroke()
        elif self.mode == "error":
            for a, b in (((-12, -12), (12, 12)), ((12, -12), (-12, 12))):
                cr.move_to(*a)
                cr.line_to(*b)
            cr.set_source_rgb(*ERR_RED)
            cr.stroke()
        else:
            self._text(cr, f"{int(frac * 100)}%", 0, 0, INK, size=15, bold=True)

        text = self.result_text if self.mode in ("done", "error") else f"{self.job_label}…"
        self._pill(cr, text, 0, R_PROG + 36, size=10, dark=True, pad=14)

    # ---- small drawing helpers ------------------------------------------------------

    def _size_text(self):
        try:
            size = sum(p.stat().st_size for p in self.files)
        except OSError:
            return ""
        for unit in ("B", "KB", "MB", "GB"):
            if size < 1024 or unit == "GB":
                return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
            size /= 1024

    def _layout(self, cr, text, size, bold, spacing=0.0):
        layout = PangoCairo.create_layout(cr)
        font = Pango.FontDescription.from_string(f"Inter, Cantarell, Sans {'Bold' if bold else ''} {size}")
        layout.set_font_description(font)
        if spacing:
            attrs = Pango.AttrList()
            attrs.insert(Pango.attr_letter_spacing_new(int(spacing * Pango.SCALE)))
            layout.set_attributes(attrs)
        layout.set_text(text, -1)
        return layout

    def _text(self, cr, text, x, y, rgb, size=10, bold=False, spacing=0.0):
        layout = self._layout(cr, text, size, bold, spacing)
        tw, th = layout.get_pixel_size()
        cr.move_to(x - tw / 2, y - th / 2)
        cr.set_source_rgb(*rgb)
        PangoCairo.show_layout(cr, layout)

    def _pill(self, cr, text, x, y, size=9, dark=False, pad=8):
        if not text:
            return
        layout = self._layout(cr, text, size, dark)
        tw, th = layout.get_pixel_size()
        w, h = tw + 2 * pad, th + 10
        _rounded_rect(cr, x - w / 2, y - h / 2, w, h, h / 2)
        cr.set_source_rgba(*((0.22, 0.12, 0.08, 0.80) if dark else (1, 1, 1, 0.95)))
        cr.fill_preserve()
        cr.set_source_rgba(1, 1, 1, 0.25 if dark else 0.9)
        cr.set_line_width(1)
        cr.stroke()
        cr.move_to(x - tw / 2, y - th / 2)
        cr.set_source_rgb(*(WHITE if dark else INK))
        PangoCairo.show_layout(cr, layout)

    def _paint_icon(self, cr, name, x, y, rgb, size=20):
        """Draw a symbolic theme icon tinted with rgb. Returns False if missing."""
        if name not in self._icons:
            pix = None
            try:
                theme = Gtk.IconTheme.get_for_display(self.get_display())
                if theme.has_icon(name):
                    icon = theme.lookup_icon(name, None, size, 1, Gtk.TextDirection.NONE, 0)
                    f = icon.get_file()
                    if f and f.get_path():
                        pix = GdkPixbuf.Pixbuf.new_from_file_at_size(f.get_path(), size, size)
            except GLib.Error:
                pix = None
            self._icons[name] = pix
        pix = self._icons[name]
        if not pix:
            return False
        cr.save()
        Gdk.cairo_set_source_pixbuf(cr, pix, x, y)
        mask = cr.get_source()
        cr.set_source_rgb(*rgb)
        cr.mask(mask)
        cr.restore()
        return True
