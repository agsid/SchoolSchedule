#!/bin/sh
# Install School Schedule for the current user (no root needed).
#   ./install.sh            create a private virtualenv and pip-install PySide6   (any distro with python3-venv)
#   ./install.sh --system   use PySide6 already installed by your distro package manager
# Alternative:  pipx install .      (then run ./install.sh --desktop-only for the menu entry)
set -eu
DIR="$(cd "$(dirname "$0")" && pwd)"
MODE=venv
for a in "$@"; do case "$a" in --system) MODE=system ;; --desktop-only) MODE=desktop ;; esac; done
PY="${PYTHON:-python3}"

distro_hint() {
  id=""; like=""
  [ -r /etc/os-release ] && . /etc/os-release && id="${ID:-}" && like="${ID_LIKE:-}"
  case " $id $like " in
    *arch*|*cachyos*|*manjaro*) echo "  Arch-based:   sudo pacman -S pyside6" ;;
    *debian*|*ubuntu*|*mint*)   echo "  Debian-based: sudo apt install python3-venv   (for the default mode)" ;;
    *fedora*|*rhel*)            echo "  Fedora:       sudo dnf install python3-pyside6" ;;
    *suse*)                     echo "  openSUSE:     sudo zypper install python3-pyside6" ;;
    *alpine*)                   echo "  Alpine:       apk add py3-pyside6   (pip wheels need glibc, so use --system)" ;;
    *nixos*|*nix*)              echo "  NixOS:        nix-shell -p python3Packages.pyside6" ;;
    *)                          echo "  Install your distro's PySide6 package (package names vary)." ;;
  esac
}

command -v "$PY" >/dev/null 2>&1 || { echo "python3 not found."; exit 1; }
"$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' || { echo "Python 3.9 or newer is required."; exit 1; }

case "$MODE" in
  venv)
    if [ ! -x "$DIR/.venv/bin/python" ]; then
      "$PY" -m venv "$DIR/.venv" || { echo "Could not create a virtualenv. Try:"; distro_hint; exit 1; }
    fi
    "$DIR/.venv/bin/pip" install -q --upgrade -r "$DIR/requirements.txt" || {
      echo "pip could not install PySide6 (unsupported platform, e.g. musl/Alpine or non-x86/arm64?). Use:  ./install.sh --system"; distro_hint; exit 1; }
    ;;
  system)
    "$PY" -c 'import PySide6.QtWidgets, PySide6.QtNetwork' 2>/dev/null || { echo "System PySide6 not found. Install it first:"; distro_hint; exit 1; }
    ;;
esac

BIN="$HOME/.local/bin"; APPS="$HOME/.local/share/applications"; ICONS="$HOME/.local/share/icons/hicolor/scalable/apps"
mkdir -p "$BIN" "$APPS" "$ICONS"
ln -sf "$DIR/school-schedule" "$BIN/school-schedule"
cp "$DIR/school_schedule/assets/school-schedule.svg" "$ICONS/school-schedule.svg"
sed "s|@EXEC@|$BIN/school-schedule|g" "$DIR/data/school-schedule.desktop.in" > "$APPS/school-schedule.desktop"
command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database "$APPS" 2>/dev/null || true
command -v gtk-update-icon-cache  >/dev/null 2>&1 && gtk-update-icon-cache -q -t "$HOME/.local/share/icons/hicolor" 2>/dev/null || true
command -v kbuildsycoca6 >/dev/null 2>&1 && kbuildsycoca6 >/dev/null 2>&1 || true

echo "Installed. Start it with:  school-schedule"
case ":$PATH:" in *":$BIN:"*) ;; *) echo "Note: $BIN is not on your PATH; add it to use the 'school-schedule' command." ;; esac
command -v notify-send >/dev/null 2>&1 || echo "Tip: install libnotify (notify-send) for the most reliable notifications."
