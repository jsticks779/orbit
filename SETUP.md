# Setup

## Requirements

- Ubuntu 24.04 or newer (GNOME, Wayland or X11)
- Python 3.10+ with GTK 4 and libadwaita bindings (installed by `setup.sh`)
- Optional: `ffmpeg` (audio/video), `libreoffice` (Office documents), `ghostscript` (smaller PDFs)

## Install

```bash
./setup.sh
```

The script:

1. installs missing system packages with `apt` (asks for your password),
2. creates a private Python environment in `~/.local/share/orbit/venv`,
3. adds the `orbit` command (`~/.local/bin/orbit`), app icon, autostart entry and the Files script,
4. asks to add you to the `input` group so drag + Shift can be detected,
5. starts Orbit and runs `orbit doctor`.

**Log out and back in once** after the first install so the `input` group applies.

## Development

```bash
python3 -m venv --system-site-packages .venv
.venv/bin/pip install -e ".[full,dev]"
.venv/bin/pytest
.venv/bin/orbit ring some-file.png   # try the ring without the service
.venv/bin/orbit                      # run the service in the foreground
```

`./setup.sh --dev` installs in editable mode, so edits in `src/` apply after restarting Orbit (`pkill -f orbit; orbit &`).

## Troubleshooting

| Problem | Fix |
|---|---|
| Nothing happens on drag + Shift | Run `orbit doctor`. If "input access" is ✗, run `./setup.sh` and log out and back in. |
| Ring opens with few or no slices | The file type isn't supported yet. Check with `orbit list FILE`. |
| "ffmpeg is not installed" | `sudo apt install ffmpeg` |
| DOCX / PPTX conversions fail | `sudo apt install libreoffice` |
| HEIC or PDF→DOCX missing | `~/.local/share/orbit/venv/bin/pip install pi-heif pdf2docx` |

## Uninstall

```bash
./setup.sh --uninstall
```
