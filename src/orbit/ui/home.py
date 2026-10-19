"""The Orbit home window: what opens when you click the app icon."""

from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, Gio, GLib, Gtk  # noqa: E402

from ..core import settings  # noqa: E402

STEPS = [
    ("1", "Start dragging any file", "From Files, your desktop, or most apps."),
    ("2", "Keep holding and tap Shift", "The Orbit card opens. Tap Shift again for Tools."),
    ("3", "Drop it on a bubble", "The new file is saved next to the original."),
]


class HomeWindow(Gtk.Window):
    def __init__(self, app):
        super().__init__(application=app, title="Orbit", default_width=520, resizable=False)
        self.app = app
        self.add_css_class("orbit-editor")
        self.add_css_class("orbit-home")

        header = Gtk.HeaderBar(decoration_layout="close:")
        header.set_title_widget(Gtk.Label(label=""))
        self.set_titlebar(header)

        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=22,
                       margin_top=6, margin_bottom=24, margin_start=28, margin_end=28)
        self.set_child(body)

        # Title and status
        top = Gtk.Box(spacing=12)
        title = Gtk.Label(label="Orbit", xalign=0, hexpand=True)
        title.add_css_class("orbit-hero")
        top.append(title)
        self.status = Gtk.Label(valign=Gtk.Align.CENTER)
        self.status.add_css_class("orbit-status")
        top.append(self.status)
        body.append(top)
        tag = Gtk.Label(label="Drag a file. Tap Shift. Drop.", xalign=0)
        tag.add_css_class("dim-label")
        body.append(tag)

        # Drop area
        drop_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, halign=Gtk.Align.FILL)
        drop_box.add_css_class("orbit-drop")
        icon = Gtk.Image(icon_name="document-send-symbolic", pixel_size=36)
        icon.add_css_class("dim-label")
        drop_box.append(icon)
        drop_box.append(Gtk.Label(label="Drop files here"))
        choose = Gtk.Button(label="Choose files…", halign=Gtk.Align.CENTER)
        choose.add_css_class("suggested-action")
        choose.connect("clicked", self._choose)
        drop_box.append(choose)
        target = Gtk.DropTarget.new(Gdk.FileList, Gdk.DragAction.COPY)
        target.connect("drop", self._dropped)
        target.connect("enter", lambda *_: (drop_box.add_css_class("hover"), Gdk.DragAction.COPY)[1])
        target.connect("leave", lambda *_: drop_box.remove_css_class("hover"))
        drop_box.add_controller(target)
        body.append(drop_box)

        # How it works
        body.append(self._section("How it works"))
        for num, head, sub in STEPS:
            row = Gtk.Box(spacing=14)
            n = Gtk.Label(label=num, valign=Gtk.Align.START)
            n.add_css_class("orbit-num")
            row.append(n)
            col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            h = Gtk.Label(label=head, xalign=0)
            h.add_css_class("orbit-strong")
            s = Gtk.Label(label=sub, xalign=0, wrap=True)
            s.add_css_class("dim-label")
            col.append(h)
            col.append(s)
            row.append(col)
            body.append(row)

        # Recent
        self.recent_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        body.append(self._section("Recent"))
        body.append(self.recent_box)

        # Settings
        body.append(self._section("Settings"))
        prefs = settings.load()
        body.append(self._switch_row("Sounds", "Soft sounds when the card opens and when a file is ready.",
                                     prefs.get("sounds", True), lambda on: settings.save("sounds", on)))
        body.append(self._switch_row("Start Orbit when I log in", "Keeps drag + Shift ready all the time.",
                                     settings.starts_at_login(), settings.set_start_at_login))

        self.refresh()
        GLib.timeout_add_seconds(2, lambda: (self.refresh(), self.get_visible())[1])

    # ---- pieces -----------------------------------------------------------------

    def _section(self, text):
        lab = Gtk.Label(label=text.upper(), xalign=0)
        lab.add_css_class("orbit-section")
        return lab

    def _switch_row(self, title, sub, active, on_change):
        row = Gtk.Box(spacing=12)
        col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, hexpand=True)
        h = Gtk.Label(label=title, xalign=0)
        h.add_css_class("orbit-strong")
        s = Gtk.Label(label=sub, xalign=0, wrap=True)
        s.add_css_class("dim-label")
        col.append(h)
        col.append(s)
        row.append(col)
        sw = Gtk.Switch(active=active, valign=Gtk.Align.CENTER)
        sw.connect("notify::active", lambda w, _p: on_change(w.get_active()))
        row.append(sw)
        return row

    def refresh(self):
        watching = bool(self.app.watcher and self.app.watcher.is_alive())
        self.status.set_label("● Drag + Shift is on" if watching else "● Card only")
        self.status.remove_css_class("off" if watching else "on")
        self.status.add_css_class("on" if watching else "off")
        child = self.recent_box.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            self.recent_box.remove(child)
            child = nxt
        items = settings.recent(5)
        if not items:
            empty = Gtk.Label(label="Files you make with Orbit will show up here.", xalign=0)
            empty.add_css_class("dim-label")
            self.recent_box.append(empty)
        for p in items:
            row = Gtk.Box(spacing=10)
            name = Gtk.Label(label=p.name, xalign=0, hexpand=True, ellipsize=3)
            row.append(name)
            where = Gtk.Label(label=str(p.parent).replace(str(Path.home()), "~"), ellipsize=1, max_width_chars=22)
            where.add_css_class("dim-label")
            row.append(where)
            show = Gtk.Button(label="Show")
            show.connect("clicked", lambda _b, path=p: self.app.show_in_files(path))
            row.append(show)
            self.recent_box.append(row)

    # ---- actions ----------------------------------------------------------------

    def _open_card(self, files):
        if files:
            self.app.open_ring([Path(f) for f in files])

    def _dropped(self, _target, value, *_):
        from ..core.portal import real_paths
        self._open_card(real_paths([f.get_path() for f in value.get_files() if f.get_path()]))
        return True

    def _choose(self, _btn):
        dialog = Gtk.FileDialog(title="Choose files for Orbit")

        def done(d, res):
            try:
                files = d.open_multiple_finish(res)
            except GLib.Error:
                return
            self._open_card([files.get_item(i).get_path() for i in range(files.get_n_items())])

        dialog.open_multiple(self, None, done)
