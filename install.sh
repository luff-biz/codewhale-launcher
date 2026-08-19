#!/usr/bin/env bash
# Installiert/aktualisiert die Codewhale-Launcher-Extension für den aktuellen Benutzer.
set -euo pipefail

UUID="codewhale-launcher@luff.biz"
SRC="$(cd "$(dirname "$0")" && pwd)/$UUID"
DEST="$HOME/.local/share/gnome-shell/extensions/$UUID"

mkdir -p "$DEST"
rsync -a --delete "$SRC"/ "$DEST"/
chmod +x "$DEST/helper/panel-data.py"

echo "Installiert nach: $DEST"

if gnome-extensions enable "$UUID" 2>/dev/null; then
    echo "Extension aktiviert."
else
    echo "Konnte noch nicht aktiviert werden — bei Erstinstallation unter Wayland:"
    echo "  1. Ab- und wieder anmelden"
    echo "  2. gnome-extensions enable $UUID"
fi
