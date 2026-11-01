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

# ---- install missing system requirements (Python, GTK4, WebKitGTK, audio/voice tools) with the distro's package manager ----
SUDO=""; [ "$(id -u)" -ne 0 ] && command -v sudo >/dev/null && SUDO="sudo"
install_requirements() {
  local req="" opt="" mgr="" inst=""
  if   command -v apt-get >/dev/null; then mgr=apt;    inst="$SUDO apt-get install -y"
       req="python3 python3-pip python3-venv python3-gi gir1.2-gtk-4.0 gir1.2-webkit-6.0 curl openssl tar"
       opt="espeak-ng pulseaudio-utils ydotool xdotool"
  elif command -v dnf >/dev/null; then mgr=dnf;        inst="$SUDO dnf install -y"
       req="python3 python3-pip python3-gobject gtk4 webkitgtk6.0 curl openssl tar"
       opt="espeak-ng pulseaudio-utils ydotool xdotool"
  elif command -v pacman >/dev/null; then mgr=pacman;  inst="$SUDO pacman -S --needed --noconfirm"
       req="python python-pip python-gobject gtk4 webkitgtk-6.0 curl openssl tar"
       opt="espeak-ng libpulse ydotool xdotool"
  elif command -v zypper >/dev/null; then mgr=zypper;  inst="$SUDO zypper --non-interactive install"
       req="python3 python3-pip python3-gobject typelib-1_0-Gtk-4_0 typelib-1_0-WebKit-6_0 curl openssl tar"
       opt="espeak-ng pulseaudio-utils ydotool xdotool"
  else echo "Unknown Linux distribution: please install Python 3, pip, GTK 4 and WebKitGTK 6 (with their Python bindings) yourself."; return 0; fi
  if command -v rpm-ostree >/dev/null && [ -e /run/ostree-booted ]; then
    echo "Immutable system (Bazzite/Silverblue style) detected: Python, GTK4 and WebKitGTK come preinstalled, skipping package installs."; return 0
  fi
  if [ -z "$SUDO" ] && [ "$(id -u)" -ne 0 ]; then echo "No sudo available: cannot install system packages automatically."; return 0; fi
  echo "Installing requirements with $mgr (may ask for your password)..."
  [ "$mgr" = apt ] && $SUDO apt-get update -y >/dev/null 2>&1 || true
  $inst $req || echo "Some required packages could not be installed; the check below will say what is missing."
  for p in $opt; do $inst "$p" >/dev/null 2>&1 || echo "(optional package '$p' not available, Jarvis may be limited)"; done
}
install_requirements

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
