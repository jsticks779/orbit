# Security and privacy

## What Orbit can see

To detect **drag + Shift** on Wayland, Orbit reads Linux input devices (`/dev/input/event*`).
This requires your user to be in the `input` group, which technically lets any program you run
read keyboard and mouse events.

Orbit's own use is deliberately narrow (`src/orbit/trigger/gesture.py`, ~100 lines, easy to audit):

- It reacts to only three events: **left mouse button down**, **left mouse button up**, **Shift down**.
- Every other key is read and discarded immediately. Nothing is stored, logged or sent anywhere.
- Orbit makes **no network connections** at all.

If you'd rather not grant this, skip the step in `setup.sh`. Orbit still works through
**Files → right-click → Scripts → Orbit** and `orbit ring FILE`.

## Files

- Orbit never modifies or deletes your original files; every result is a new file next to it.
- Conversions run locally with Pillow, PyMuPDF, ffmpeg, Ghostscript and LibreOffice.
  Opening untrusted files carries the same risk as opening them in those tools; keep your system updated.

## Reporting a vulnerability

Please open a private security advisory on GitHub (Security → Report a vulnerability)
instead of a public issue.
