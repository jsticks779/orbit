"""Map document-portal paths back to the real file.

Some apps hand dropped files over through the document portal, so we get
`/run/user/1000/doc/ab12cd/photo.png` instead of `~/Pictures/photo.png`.
Writing next to that hidden copy would make the result invisible, so we ask
the portal where the file really lives.
"""

import os
from pathlib import Path

DOC_ROOT = Path(f"/run/user/{os.getuid()}/doc")


def real_path(path: Path) -> Path:
    if DOC_ROOT not in path.parents:
        return path
    try:
        host = os.getxattr(path, "user.document-portal.host-path").decode().rstrip("\0")
        if host and Path(host).exists():
            return Path(host)
    except OSError:
        pass
    try:
        doc_id = path.relative_to(DOC_ROOT).parts[0]
        from gi.repository import Gio, GLib
        bus = Gio.bus_get_sync(Gio.BusType.SESSION)
        res = bus.call_sync("org.freedesktop.portal.Documents", "/org/freedesktop/portal/documents",
                            "org.freedesktop.portal.Documents", "GetHostPaths",
                            GLib.Variant("(as)", ([doc_id],)), None, 0, 2000, None)
        raw = res.unpack()[0].get(doc_id)
        if raw:
            host = Path(bytes(raw).rstrip(b"\0").decode())
            if host.exists():
                return host
    except Exception:
        pass
    return path


def real_paths(paths):
    return [real_path(Path(p)) for p in paths]
