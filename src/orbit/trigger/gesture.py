"""Detect the drag + Shift gesture.

Wayland does not let apps watch global input, so we read the kernel input
devices (evdev) directly. That needs the user to be in the `input` group.
We only look at three things: left mouse button down/up and Shift
down. Nothing is logged or stored. See SECURITY.md.
"""

import logging
import selectors
import threading
import time

log = logging.getLogger(__name__)

HOLD_BEFORE_SHIFT = 0.12   # seconds the button must be held: a drag, not a click
RESCAN_EVERY = 5.0         # pick up mice and keyboards plugged in later


class GestureWatcher(threading.Thread):
    """Calls on_summon() for drag + Shift, on_shift() for Shift while dragging, on_release() on button up."""

    def __init__(self, on_summon, on_shift, on_release):
        super().__init__(daemon=True, name="orbit-gesture")
        self.on_summon, self.on_shift, self.on_release = on_summon, on_shift, on_release
        self.sel = selectors.DefaultSelector()
        self.devices = {}
        self.button_down_at = None
        self.summoned = False
        self.error = None

    def available(self) -> bool:
        try:
            self._scan()
        except ImportError:
            self.error = "python evdev is not installed"
            return False
        if not self.devices:
            self.error = "cannot read input devices (are you in the 'input' group?)"
            return False
        return True

    def _scan(self):
        import evdev
        from evdev import ecodes as e
        for path in evdev.list_devices():
            if path in self.devices:
                continue
            try:
                dev = evdev.InputDevice(path)
            except OSError:
                continue
            keys = dev.capabilities().get(e.EV_KEY, [])
            if e.BTN_LEFT in keys or e.KEY_LEFTSHIFT in keys:
                self.devices[path] = dev
                self.sel.register(dev, selectors.EVENT_READ)
            else:
                dev.close()

    def _drop(self, dev):
        self.sel.unregister(dev)
        self.devices.pop(dev.path, None)
        dev.close()

    def run(self):
        from evdev import ecodes as e
        shifts = {e.KEY_LEFTSHIFT, e.KEY_RIGHTSHIFT}
        last_scan = time.monotonic()
        while True:
            for key, _ in self.sel.select(timeout=1.0):
                dev = key.fileobj
                try:
                    events = list(dev.read())
                except OSError:  # unplugged
                    self._drop(dev)
                    continue
                for ev in events:
                    if ev.type != e.EV_KEY:
                        continue
                    if ev.code == e.BTN_LEFT:
                        if ev.value == 1:
                            self.button_down_at = time.monotonic()
                        elif ev.value == 0:
                            self.button_down_at = None
                            if self.summoned:
                                self.summoned = False
                                self.on_release()
                    elif ev.code in shifts and ev.value == 1 and self.button_down_at:
                        if self.summoned:
                            self.on_shift()
                        elif time.monotonic() - self.button_down_at >= HOLD_BEFORE_SHIFT:
                            self.summoned = True
                            self.on_summon()
            if time.monotonic() - last_scan > RESCAN_EVERY:
                self._scan()
                last_scan = time.monotonic()
