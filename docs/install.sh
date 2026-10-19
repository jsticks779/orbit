#!/usr/bin/env bash
# Orbit one-line installer:
#   curl -fsSL https://jsticks779.github.io/orbit/install.sh | bash
#
# Downloads the latest release into ~/.local/share/orbit/src and runs its setup.sh.
# Read setup.sh first if you like: https://github.com/jsticks779/orbit/blob/main/setup.sh
set -euo pipefail

REPO="jsticks779/orbit"
DEST="$HOME/.local/share/orbit/src"
RELEASE_URL="https://github.com/$REPO/releases/latest/download/orbit.tar.gz"
MAIN_URL="https://github.com/$REPO/archive/refs/heads/main.tar.gz"

bold() { printf '\033[1m%s\033[0m\n' "$*"; }
fail() { printf '\033[1;31m!\033[0m %s\n' "$*" >&2; exit 1; }

command -v apt-get >/dev/null || fail "Orbit currently supports Ubuntu (and other apt-based systems)."
command -v python3 >/dev/null || fail "python3 is missing: sudo apt install python3"
command -v curl >/dev/null || fail "curl is missing: sudo apt install curl"

bold "Downloading Orbit…"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
if ! curl -fsSL --retry 5 --retry-delay 2 "$RELEASE_URL" -o "$TMP/orbit.tar.gz"; then
  curl -fsSL --retry 5 --retry-delay 2 "$MAIN_URL" -o "$TMP/orbit.tar.gz" || fail "Download failed. Check your connection and try again."
fi
mkdir -p "$TMP/x"
tar -xzf "$TMP/orbit.tar.gz" -C "$TMP/x"
SRC="$(dirname "$(find "$TMP/x" -maxdepth 2 -name setup.sh | head -1)")"
[[ -f "$SRC/setup.sh" ]] || fail "The download looks incomplete. Please try again."

rm -rf "$DEST"
mkdir -p "$(dirname "$DEST")"
mv "$SRC" "$DEST"

bold "Installing…"
# setup.sh may ask for your password (system packages) and one yes/no question,
# so give it the real terminal even though this script came through a pipe.
if (exec < /dev/tty) 2>/dev/null; then
  bash "$DEST/setup.sh" < /dev/tty
else
  bash "$DEST/setup.sh"
fi

echo
bold "Done. Open a new terminal and type:  orbit"
