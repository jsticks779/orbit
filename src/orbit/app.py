"""The Orbit service: one running instance that owns the ring, editors and jobs."""

import logging
import threading
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk  # noqa: E402

from . import APP_ID  # noqa: E402
from .actions import ActionError  # noqa: E402
from .core.actions import Action  # noqa: E402

log = logging.getLogger("orbit")


class OrbitApp(Adw.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE)
        self.ring = None
        self.watcher = None
        self._held = False
        act = Gio.SimpleAction.new("show-file", GLib.VariantType.new("s"))
        act.connect("activate", lambda _a, p: self.show_in_files(p.get_string()))
        self.add_action(act)

    # ---- startup -------------------------------------------------------------

    def do_startup(self):
        Adw.Application.do_startup(self)
        Adw.StyleManager.get_default().set_color_scheme(Adw.ColorScheme.DEFAULT)  # follow system
        css = Gtk.CssProvider()
        css.load_from_path(str(Path(__file__).parent / "ui" / "style.css"))
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), css,
                                                  Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    def do_command_line(self, cmd):
        args = cmd.get_arguments()[1:]
        if args and args[0] == "--ring":
            files = [Path(a) for a in args[1:]]
            self.open_ring(files or None)  # without the service, quits when closed
        else:
            self.start_service()
        return 0

    def start_service(self):
        if self._held:
            return
        self._held = True
        self.hold()  # keep running with no windows
        from .trigger.gesture import GestureWatcher
        self.watcher = GestureWatcher(
            on_summon=lambda: GLib.idle_add(self._summon),
            on_shift=lambda: GLib.idle_add(self._shift),
            on_release=lambda: GLib.idle_add(self._release),
        )
        if self.watcher.available():
            self.watcher.start()
            log.info("Orbit is running. Drag a file and press Shift.")
        else:
            self.notify("Orbit can't see drag + Shift yet",
                        f"{self.watcher.error}. Run setup.sh and log in again. "
                        "Right-click files → Scripts → Orbit still works.")

    # ---- the ring ------------------------------------------------------------

    def open_ring(self, files=None):
        from .ui.ring import RingWindow
        if self.ring:
            self.ring.close()
        self.ring = RingWindow(self, files)
        self.ring.connect("close-request", self._ring_closed)
        self.ring.show_ring()

    def _ring_closed(self, win):
        if self.ring is win:
            self.ring = None
        return False

    def _summon(self):
        log.info("drag + Shift detected: opening ring")
        if not self.ring:
            self.open_ring()

    def _shift(self):
        if self.ring:
            self.ring.next_page()

    def _release(self):
        log.debug("mouse released")
        if self.ring:
            self.ring.released()

    # ---- running actions -----------------------------------------------------

    def perform(self, action: Action, files: list[Path], ring=None):
        from .core.portal import real_paths
        files = real_paths(files)
        log.info("%s on %s", action.id, ", ".join(p.name for p in files))
        if action.dialog:
            from .ui.editors import EDITORS
            try:
                EDITORS[action.dialog](self, files[0]).present()
            except Exception as e:  # unreadable image etc.
                self.fail(e)
            return
        self.run_job(lambda: action.run(files), action.label, ring)

    def run_job(self, fn, label: str, ring=None):
        """Run fn() in a worker thread with a live progress circle."""
        from .core import progress
        from .ui.ring import RingWindow
        if ring is None:  # e.g. from an editor: show the circle mid-screen
            ring = RingWindow(self, progress_only=True)
            ring.present()
        ring.start_progress(label)
        self.hold()

        def work():
            progress.set_callback(lambda f: GLib.idle_add(ring.set_progress, f))
            try:
                outs = fn()
                GLib.idle_add(self._finished, ring, outs, None)
            except Exception as e:
                log.exception("%s failed", label)
                GLib.idle_add(self._finished, ring, [], e)
            finally:
                progress.set_callback(None)
                GLib.idle_add(self.release)

        threading.Thread(target=work, daemon=True).start()

    def _finished(self, ring, outs, err):
        if err:
            msg = str(err) if isinstance(err, ActionError) else "Something went wrong"
            ring.finish(False, msg)
            self.fail(err)
        else:
            name = outs[0].name if len(outs) == 1 else f"{len(outs)} files saved"
            ring.finish(True, name if outs else "Done", outs)
            self.done(outs)
        return False

    def done(self, outs: list[Path]):
        if not outs:
            return
        first = outs[0]
        title = f"Saved {first.name}" if len(outs) == 1 else f"Saved {len(outs)} files"
        self.notify(title, str(first.parent), show=first)

    def fail(self, err: Exception):
        msg = str(err) if isinstance(err, ActionError) else f"{type(err).__name__}: {err}"
        self.notify("Orbit couldn't do that", msg)

    def notify(self, title, body="", show: Path | None = None):
        n = Gio.Notification.new(title)
        n.set_body(body)
        if show:
            n.add_button_with_target("Show in Files", "app.show-file", GLib.Variant.new_string(str(show)))
        self.send_notification(None, n)
        log.info("%s %s", title, body)

    def show_in_files(self, path):
        path = str(path)
        uri = Gio.File.new_for_path(path).get_uri()
        try:
            Gio.bus_get_sync(Gio.BusType.SESSION).call_sync(
                "org.freedesktop.FileManager1", "/org/freedesktop/FileManager1",
                "org.freedesktop.FileManager1", "ShowItems",
                GLib.Variant("(ass)", ([uri], "")), None, Gio.DBusCallFlags.NONE, -1, None)
        except GLib.Error:
            Gio.AppInfo.launch_default_for_uri(Gio.File.new_for_path(path).get_parent().get_uri(), None)
