#!/usr/bin/env bash
# Installs Claude Linux for the current user (no root needed).
#   ./install.sh              install or update
#   ./install.sh --uninstall  remove the app (your chats and settings are kept)
set -euo pipefail

APP_DIR="$HOME/.local/share/claude-linux-app"
BIN="$HOME/.local/bin/claude-linux"
APPS="$HOME/.local/share/applications"
ICONS="$HOME/.local/share/icons/hicolor/scalable/apps"
DESKTOP="$APPS/dev.nein.ClaudeLinux.desktop"
HERE="$(cd "$(dirname "$0")" && pwd)"

if [ "${1:-}" = "--uninstall" ]; then
  rm -rf "$APP_DIR" "$BIN" "$DESKTOP" "$ICONS/dev.nein.ClaudeLinux.svg"
  command -v update-desktop-database >/dev/null && update-desktop-database "$APPS" || true
  echo "Removed Claude Linux. Your chats and settings are still in ~/.local/share/claude-linux (delete that folder to remove them too)."
  exit 0
fi

echo "Checking requirements..."
python3 - <<'PY' || { echo "Cannot continue. Needs Python 3 with GTK 4.10+ and WebKitGTK 6 (2.40+): Python 3 with GTK 4 and WebKitGTK 6 (python3-gobject, webkitgtk6.0). On Fedora/Bazzite they are preinstalled; on Ubuntu: sudo apt install python3-gi gir1.2-gtk-4.0 gir1.2-webkit-6.0"; exit 1; }
import gi
gi.require_version("Gtk", "4.0"); gi.require_version("WebKit", "6.0")
from gi.repository import Gtk, WebKit
import sys
if (Gtk.get_major_version(), Gtk.get_minor_version()) < (4, 10) or (WebKit.get_major_version(), WebKit.get_minor_version()) < (2, 40):
    print("Your GTK (%d.%d) or WebKitGTK (%d.%d) is too old: Claude Linux needs GTK 4.10+ and WebKitGTK 2.40+ (Ubuntu 24.04+, Fedora 38+, Debian 13+)." % (Gtk.get_major_version(), Gtk.get_minor_version(), WebKit.get_major_version(), WebKit.get_minor_version()))
    sys.exit(1)
PY
if ! command -v claude >/dev/null && [ ! -x "$HOME/.local/bin/claude" ]; then
  echo "Note: the Claude Code CLI ('claude') was not found. Install it from https://claude.com/claude-code and run 'claude auth login' once, then Claude Linux will work."
fi

echo "Installing to $APP_DIR ..."
rm -rf "$APP_DIR"; mkdir -p "$APP_DIR" "$APPS" "$ICONS" "$HOME/.local/bin"
for f in app.py build.py icon.svg claude_linux ui; do cp -r "$HERE/$f" "$APP_DIR/"; done
find "$APP_DIR" -name __pycache__ -prune -exec rm -rf {} +
cp "$HERE/icon.svg" "$ICONS/dev.nein.ClaudeLinux.svg"

cat > "$BIN" <<WRAP
#!/usr/bin/env bash
cd "$APP_DIR" && exec python3 app.py "\$@"
WRAP
chmod +x "$BIN"

cat > "$DESKTOP" <<DESK
[Desktop Entry]
Type=Application
Name=Claude Linux
Comment=A desktop window for Claude Code
Exec="$BIN" %U
Icon=dev.nein.ClaudeLinux
Terminal=false
Categories=Development;
Keywords=claude;ai;code;chat;
StartupWMClass=dev.nein.ClaudeLinux
StartupNotify=true
X-GNOME-UsesNotifications=true
Actions=NewSession;

[Desktop Action NewSession]
Name=New session
Exec="$BIN" --new
DESK
command -v update-desktop-database >/dev/null && update-desktop-database "$APPS" || true
command -v gtk-update-icon-cache >/dev/null && gtk-update-icon-cache -q -t "$HOME/.local/share/icons/hicolor" || true

echo "Done. Start it from your app menu (\"Claude Linux\") or run: claude-linux"
case ":$PATH:" in *":$HOME/.local/bin:"*) ;; *) echo "(add ~/.local/bin to your PATH to use the 'claude-linux' command)";; esac
