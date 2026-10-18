# Architecture

```
orbit/
├── setup.sh                 one-command installer (and --uninstall)
├── pyproject.toml           package + dependencies
├── src/orbit/
│   ├── cli.py               `orbit`, `orbit ring`, `orbit list`, `orbit run`, `orbit doctor`
│   ├── app.py               the background service (single instance, GTK 4 + libadwaita)
│   ├── core/
│   │   ├── actions.py       Action registry: which slices fit which files
│   │   ├── filetypes.py     image / pdf / document / audio / video detection
│   │   └── naming.py        safe output names: "Page 001 Cropped.jpg", "(2)"...
│   ├── actions/             the actual work, no UI code
│   │   ├── image.py         Pillow conversions + tools
│   │   ├── backdrop.py      "Add BG" renderer (used by preview and save)
│   │   ├── document.py      PyMuPDF, pdf2docx, Ghostscript, LibreOffice
│   │   ├── media.py         ffmpeg audio/video
│   │   └── archive.py       ZIP for any file
│   ├── trigger/
│   │   └── gesture.py       drag + Shift detection via evdev
│   └── ui/
│       ├── ring.py          the transparent overlay and radial menu
│       ├── editors.py       Crop and Add BG windows
│       └── style.css
├── data/                    icon, .desktop launcher, autostart, Files script
├── tests/                   pytest, no display needed
└── docs/                    screenshots
```

## How a drag + Shift becomes a new file

1. **`trigger/gesture.py`** reads `/dev/input/event*` in a background thread.
   When Shift goes down while the left button has been held for more than 120 ms, it calls `on_summon`.
   Wayland gives apps no global input access, so this is the only reliable way to see the gesture on GNOME.
2. **`app.py`** opens a **`RingWindow`**: a fullscreen, fully transparent window.
3. The drag in progress enters that window. GTK's `DropTarget` (with `preload`) reports the cursor
   position and the file list **before** the drop, so the ring is drawn under the cursor with
   only the actions that fit those files (`core.actions.pages_for`).
4. On drop, the slice under the cursor decides the `Action`. Plain actions run in a worker thread;
   `dialog` actions open an editor. The result is announced with a notification that has a **Show in Files** button.
5. If the mouse button is released without a drop, or nothing enters within 8 s, the overlay closes.

## Adding an action

```python
# src/orbit/actions/image.py
@action("image.sepia", "Sepia", [Kind.IMAGE], page=TOOLS, order=7)
def sepia(paths):
    return [save_as(p, "jpg", "Sepia", ImageOps.colorize(ImageOps.grayscale(open_image(p)), "#2b1d0e", "#f3e0c0"))
            for p in paths]
```

Rules every action follows:
- Take a list of paths and return the list of files it created.
- Write **next to the source** using `core.naming.output_path`, so nothing is ever overwritten.
- Raise `ActionError("friendly message")` for problems the user can fix (missing tool, bad file).
- Import heavy or optional libraries inside the function, so a missing extra only disables that slice.
