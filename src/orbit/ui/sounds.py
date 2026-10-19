"""Gentle interface sounds, played with GStreamer.

Turn them off with ORBIT_SOUNDS=0. Missing GStreamer just means silence.
"""

import os
import time
from pathlib import Path

DIR = Path(__file__).resolve().parent.parent / "sounds"
VOLUME = {"hover": 0.5, "switch": 0.6, "open": 0.7, "start": 0.7, "success": 0.8, "error": 0.8}
_players = {}
_last = {}
_ok = None


def _init():
    global _ok
    if _ok is None:
        try:
            import gi
            gi.require_version("Gst", "1.0")
            from gi.repository import Gst
            Gst.init(None)
            _ok = True
        except (ImportError, ValueError):
            _ok = False
    return _ok


def play(name: str):
    if os.environ.get("ORBIT_SOUNDS", "1") == "0" or not _init():
        return
    from ..core import settings
    if not settings.load().get("sounds", True):
        return
    now = time.monotonic()
    if now - _last.get(name, 0) < (0.07 if name == "hover" else 0.15):  # never machine-gun
        return
    _last[name] = now
    path = DIR / f"{name}.wav"
    if not path.exists():
        return
    from gi.repository import Gst
    player = _players.get(name)
    if player is None:
        player = Gst.ElementFactory.make("playbin", None)
        if player is None:
            return
        player.set_property("uri", path.as_uri())
        player.set_property("volume", VOLUME.get(name, 0.7))
        _players[name] = player
    player.set_state(Gst.State.NULL)
    player.set_state(Gst.State.PLAYING)
