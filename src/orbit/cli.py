"""Command line entry point.

    orbit                      make sure Orbit is running and show help
    orbit service              run the background service (used by autostart)
    orbit ring [FILES...]      open the ring now (drop zone, or for FILES)
    orbit list FILES...        show which actions fit these files
    orbit run ACTION FILES...  run one action, e.g. `orbit run image.to_png a.jpg`
    orbit doctor               check that everything Orbit needs is installed
"""

import argparse
import shutil
import sys
from pathlib import Path

from . import __version__


def _paths(items):
    paths = [Path(p).expanduser().resolve() for p in items]
    missing = [p for p in paths if not p.exists()]
    if missing:
        sys.exit(f"orbit: not found: {', '.join(map(str, missing))}")
    return paths


def cmd_list(args):
    from .core.actions import pages_for
    for n, page in enumerate(pages_for(_paths(args.files))):
        print(["Convert", "Tools"][n] if len(page) else "")
        for a in page:
            print(f"  {a.id:<22} {a.label}{'  (opens editor)' if a.dialog else ''}")


def cmd_run(args):
    from .actions import ActionError
    from .core.actions import get
    act = get(args.action)
    if act.dialog:
        sys.exit(f"orbit: {act.label} needs the editor, use `orbit ring FILE` instead")
    try:
        for out in act.run(_paths(args.files)):
            print(out)
    except ActionError as e:
        sys.exit(f"orbit: {e}")


BANNER = """
  \033[1morbit\033[0m {version}   drag. shift. done.

  {status}

  \033[2mDrag any file, keep holding, and tap Shift.\033[0m

  orbit ring FILE            open the card for a file
  orbit list FILE            what can Orbit do with it?
  orbit run ACTION FILE      do it right here, e.g. orbit run image.to_webp photo.jpg
  orbit doctor               check your setup
"""


def cmd_welcome():
    """Typed `orbit`: start the service in the background if needed, then say hello."""
    import subprocess
    running = subprocess.run(["gdbus", "call", "--session", "--dest", "org.freedesktop.DBus",
                              "--object-path", "/org/freedesktop/DBus", "--method",
                              "org.freedesktop.DBus.NameHasOwner", "io.github.jsticks779.Orbit"],
                             capture_output=True, text=True).stdout
    if "true" in running:
        status = "\033[32m●\033[0m Orbit is running."
    else:
        subprocess.Popen([sys.argv[0], "service"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True)
        status = "\033[32m●\033[0m Orbit started."
    print(BANNER.format(version=__version__, status=status))
    return 0


def cmd_doctor(_args):
    import os
    checks = []
    for mod, why in [("gi", "the interface (sudo apt install python3-gi gir1.2-adw-1)"),
                     ("PIL", "images"), ("pymupdf", "PDFs"), ("evdev", "drag + Shift detection"),
                     ("pdf2docx", "PDF to DOCX (optional)"), ("pillow_heif", "HEIC images (optional)")]:
        try:
            __import__(mod)
            checks.append((True, mod, why))
        except ImportError:
            checks.append((False, mod, why))
    for tool, why in [("ffmpeg", "audio and video"), ("soffice", "office documents"), ("gs", "smaller PDFs")]:
        checks.append((bool(shutil.which(tool)), tool, why))
    readable = any(os.access(f"/dev/input/{d}", os.R_OK) for d in os.listdir("/dev/input") if d.startswith("event"))
    import grp
    import pwd
    try:
        member = pwd.getpwuid(os.getuid()).pw_name in grp.getgrnam("input").gr_mem
    except KeyError:
        member = False
    if readable:
        checks.append((True, "input access", "drag + Shift"))
    elif member:  # in the group; Orbit is started with it via `sg`, a re-login makes it permanent
        checks.append((True, "input access", "drag + Shift (active for Orbit now)"))
    else:
        checks.append((False, "input access", "drag + Shift: run setup.sh"))
    for ok, name, why in checks:
        print(f"  {'✓' if ok else '✗'} {name:<14} {why}")
    return 0 if all(ok for ok, *_ in checks[:4]) else 1


def _own_look():
    """Ignore ~/.config/gtk-4.0/gtk.css: theme packs (e.g. WhiteSur-Dark) put CSS
    there that repaints every GTK app. Orbit keeps its own light design."""
    import os
    from pathlib import Path
    home = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    if (home / "gtk-4.0" / "gtk.css").exists():
        private = Path.home() / ".local" / "share" / "orbit" / "gtk-config"
        private.mkdir(parents=True, exist_ok=True)
        os.environ["XDG_CONFIG_HOME"] = str(private)


def _make_dumpable():
    """Started via `sg input` (setgid) the process is non-dumpable, and the
    document portal then can't hand us dropped files. Undo that."""
    try:
        import ctypes
        ctypes.CDLL(None).prctl(4, 1, 0, 0, 0)  # PR_SET_DUMPABLE = 4
    except Exception:
        pass


def main(argv=None):
    parser = argparse.ArgumentParser(prog="orbit", description="Convert and edit files with a drag + Shift.")
    parser.add_argument("--version", action="version", version=f"orbit {__version__}")
    sub = parser.add_subparsers(dest="cmd")
    ring = sub.add_parser("ring", help="open the ring now")
    ring.add_argument("files", nargs="*")
    sub.add_parser("list", help="list actions for files").add_argument("files", nargs="+")
    run = sub.add_parser("run", help="run an action")
    run.add_argument("action")
    run.add_argument("files", nargs="+")
    sub.add_parser("doctor", help="check dependencies")
    sub.add_parser("service", help="run the background service")
    args = parser.parse_args(argv)

    if args.cmd == "list":
        return cmd_list(args)
    if args.cmd == "run":
        return cmd_run(args)
    if args.cmd == "doctor":
        return cmd_doctor(args)

    if args.cmd is None:
        return cmd_welcome()

    import logging
    import os
    logging.basicConfig(level=logging.DEBUG if os.environ.get("ORBIT_DEBUG") else logging.INFO,
                        format="%(asctime)s orbit: %(message)s", datefmt="%H:%M:%S")
    logging.getLogger("PIL").setLevel(logging.INFO)
    _make_dumpable()
    _own_look()
    from .app import OrbitApp
    app_argv = [sys.argv[0]]
    if args.cmd == "ring":
        app_argv += ["--ring", *[str(p) for p in _paths(args.files)]] if args.files else ["--ring"]
    return OrbitApp().run(app_argv)
