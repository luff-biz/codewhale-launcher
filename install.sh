#!/usr/bin/env bash
# Installs/updates the Codewhale Launcher extension for the current user.
set -euo pipefail

UUID="codewhale-launcher@luff.biz"
ROOT="$(cd "$(dirname "$0")" && pwd)"
SRC="$ROOT/$UUID"
DEST="$HOME/.local/share/gnome-shell/extensions/$UUID"

mkdir -p "$DEST"
rsync -a --delete "$SRC"/ "$DEST"/
chmod +x "$DEST/helper/panel-data.py"

# Compile translations (gettext domain = extension UUID)
if command -v msgfmt >/dev/null; then
    for po in "$ROOT"/po/*.po; do
        lang="$(basename "$po" .po)"
        mkdir -p "$DEST/locale/$lang/LC_MESSAGES"
        msgfmt -o "$DEST/locale/$lang/LC_MESSAGES/$UUID.mo" "$po"
    done
else
    echo "Warning: msgfmt not found — translations were not compiled."
fi

echo "Installed to: $DEST"

if gnome-extensions enable "$UUID" 2>/dev/null; then
    echo "Extension enabled."
else
    echo "Could not enable yet — on first install under Wayland:"
    echo "  1. Log out and back in"
    echo "  2. gnome-extensions enable $UUID"
fi
