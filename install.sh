#!/usr/bin/env bash
# Installs/updates the Codewhale Launcher extension for the current user.
set -euo pipefail

UUID="codewhale-launcher@luff.biz"
SRC="$(cd "$(dirname "$0")" && pwd)/$UUID"
DEST="$HOME/.local/share/gnome-shell/extensions/$UUID"

mkdir -p "$DEST"
rsync -a --delete "$SRC"/ "$DEST"/
chmod +x "$DEST/helper/panel-data.py"

echo "Installed to: $DEST"

if gnome-extensions enable "$UUID" 2>/dev/null; then
    echo "Extension enabled."
else
    echo "Could not enable yet — on first install under Wayland:"
    echo "  1. Log out and back in"
    echo "  2. gnome-extensions enable $UUID"
fi
