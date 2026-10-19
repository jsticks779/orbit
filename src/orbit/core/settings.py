"""Tiny settings and history store (~/.config/orbit, ~/.local/state/orbit)."""

import json
import os
from pathlib import Path

CONFIG = Path(os.environ.get("XDG_CONFIG_HOME_ORIG", Path.home() / ".config")) / "orbit" / "settings.json"
STATE = Path.home() / ".local" / "state" / "orbit" / "recent.json"
AUTOSTART = Path.home() / ".config" / "autostart" / "orbit.desktop"
DEFAULTS = {"sounds": True}


def load() -> dict:
    try:
        return {**DEFAULTS, **json.loads(CONFIG.read_text())}
    except (OSError, ValueError):
        return dict(DEFAULTS)


def save(key: str, value) -> None:
    data = load()
    data[key] = value
    CONFIG.parent.mkdir(parents=True, exist_ok=True)
    CONFIG.write_text(json.dumps(data, indent=2))


def recent(limit=8) -> list[Path]:
    try:
        items = [Path(p) for p in json.loads(STATE.read_text())]
    except (OSError, ValueError):
        return []
    return [p for p in items if p.exists()][:limit]


def add_recent(paths) -> None:
    items = [str(p) for p in paths] + [str(p) for p in recent(50)]
    seen, out = set(), []
    for p in items:
        if p not in seen:
            seen.add(p)
            out.append(p)
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(out[:50]))


def starts_at_login() -> bool:
    return AUTOSTART.exists() and "X-GNOME-Autostart-enabled=false" not in AUTOSTART.read_text()


def set_start_at_login(on: bool) -> None:
    if not AUTOSTART.exists():
        return
    lines = [ln for ln in AUTOSTART.read_text().splitlines() if not ln.startswith("X-GNOME-Autostart-enabled")]
    lines.append(f"X-GNOME-Autostart-enabled={'true' if on else 'false'}")
    AUTOSTART.write_text("\n".join(lines) + "\n")
