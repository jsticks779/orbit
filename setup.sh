#!/usr/bin/env bash
# Orbit installer for Ubuntu (24.04+).
#   ./setup.sh             install for the current user
#   ./setup.sh --dev       install in editable mode (changes in src/ apply live)
#   ./setup.sh --uninstall remove Orbit
set -euo pipefail

APP_ID="io.github.jsticks779.Orbit"
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PREFIX="$HOME/.local"
VENV="$PREFIX/share/orbit/venv"
BIN="$PREFIX/bin/orbit"
AUTOSTART="$HOME/.config/autostart/orbit.desktop"
NAUTILUS="$HOME/.local/share/nautilus/scripts/Orbit"

say()  { printf '\033[1;33m●\033[0m %s\n' "$*"; }
ok()   { printf '\033[1;32m✓\033[0m %s\n' "$*"; }
warn() { printf '\033[1;31m!\033[0m %s\n' "$*"; }

if [[ "${1:-}" == "--uninstall" ]]; then
  pkill -f "$VENV/bin/orbit" 2>/dev/null || true
  rm -rf "$PREFIX/share/orbit" "$BIN" "$AUTOSTART" "$NAUTILUS" \
    "$PREFIX/share/applications/$APP_ID.desktop" \
    "$PREFIX/share/icons/hicolor/scalable/apps/$APP_ID.svg"
  ok "Orbit removed. (You are still in the 'input' group; remove with: sudo gpasswd -d $USER input)"
  exit 0
fi

# 1. System packages ----------------------------------------------------------
NEED=()
for pkg in python3-venv python3-gi gir1.2-gtk-4.0 gir1.2-adw-1 ffmpeg ghostscript; do
  dpkg -s "$pkg" &>/dev/null || NEED+=("$pkg")
done
if ((${#NEED[@]})); then
  say "Installing system packages: ${NEED[*]}"
  sudo apt-get update -qq && sudo apt-get install -y "${NEED[@]}"
fi
command -v soffice >/dev/null || warn "LibreOffice not found: DOCX/ODT/PPTX conversions need it (sudo apt install libreoffice)."

# 2. Python environment -------------------------------------------------------
say "Creating Python environment in $VENV"
python3 -m venv --system-site-packages "$VENV"
"$VENV/bin/pip" install -q --upgrade pip
MODE=(); [[ "${1:-}" == "--dev" ]] && MODE=(-e)
if ! "$VENV/bin/pip" install -q --timeout 120 "${MODE[@]}" "$REPO[full]"; then
  warn "Optional extras (PDF→DOCX, HEIC) failed to install; installing the core."
  "$VENV/bin/pip" install -q --timeout 120 "${MODE[@]}" "$REPO"
fi
mkdir -p "$(dirname "$BIN")"
ln -sf "$VENV/bin/orbit" "$BIN"
ok "Installed the 'orbit' command"

# 3. Desktop integration ------------------------------------------------------
install -Dm644 "$REPO/data/icons/$APP_ID.svg" "$PREFIX/share/icons/hicolor/scalable/apps/$APP_ID.svg"
sed "s|^Exec=orbit|Exec=$BIN|" "$REPO/data/$APP_ID.desktop" | install -Dm644 /dev/stdin "$PREFIX/share/applications/$APP_ID.desktop"
sed "s|^Exec=orbit|Exec=$BIN|" "$REPO/data/orbit-autostart.desktop" | install -Dm644 /dev/stdin "$AUTOSTART"
sed "s|exec orbit|exec $BIN|" "$REPO/data/nautilus/Orbit" | install -Dm755 /dev/stdin "$NAUTILUS"
gtk4-update-icon-cache -q "$PREFIX/share/icons/hicolor" 2>/dev/null || true
update-desktop-database -q "$PREFIX/share/applications" 2>/dev/null || true
ok "Added app icon, autostart, and Files → Scripts → Orbit"

# 4. Permission to see drag + Shift ------------------------------------------
RELOGIN=0
if ! id -nG "$USER" | grep -qw input; then
  say "Orbit reads mouse button and Shift key events to detect drag + Shift."
  say "That needs your user in the 'input' group (see SECURITY.md)."
  yn=n
  if [[ -t 0 ]]; then
    read -rp "  Add $USER to the input group now? [Y/n] " yn || yn=n
    yn="${yn:-Y}"
  else
    warn "Not interactive. Later run: sudo usermod -aG input $USER"
  fi
  if [[ "$yn" =~ ^[Yy]$ ]]; then
    sudo usermod -aG input "$USER" && RELOGIN=1 && ok "Added. Log out and back in once."
  else
    warn "Skipped. Drag + Shift won't work, but right-click → Scripts → Orbit will."
  fi
fi

# 5. Start ---------------------------------------------------------------------
pkill -f "$VENV/bin/orbit" 2>/dev/null || true
(setsid "$BIN" >/dev/null 2>&1 &)
echo
"$BIN" doctor || true
echo
ok "Orbit is ready. Drag any file, keep holding, and tap Shift."
((RELOGIN)) && warn "Log out and back in first so the new permission applies."
exit 0
