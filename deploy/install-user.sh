#!/bin/sh
# Run ON THE UNO Q as the login user. Needs no sudo and no systemd: it installs
# a single desktop autostart entry, and kiosk.sh brings up both the server and
# the browser when the desktop session starts.
set -e

SRC=$(cd "$(dirname "$0")/.." && pwd)
PORT="${PORT:-8080}"

echo "installing from $SRC (user: $(id -un), port: $PORT)"

command -v chromium >/dev/null 2>&1 || command -v chromium-browser >/dev/null 2>&1 || \
  echo "WARNING: no chromium found -- install it with: sudo apt install -y chromium" >&2

chmod +x "$SRC/deploy/kiosk.sh"

mkdir -p "$HOME/.config/autostart"
cat > "$HOME/.config/autostart/robotdog-face.desktop" <<DESK
[Desktop Entry]
Type=Application
Name=Robot Dog Face
Comment=Animated eyes on the attached panel
Exec=env PORT=$PORT $SRC/deploy/kiosk.sh
X-GNOME-Autostart-enabled=true
NoDisplay=true
DESK

echo "autostart entry -> $HOME/.config/autostart/robotdog-face.desktop"
echo
echo "the face comes up on its own when the desktop session starts."
echo "to bring it up right now on an attached monitor:"
echo "  $SRC/deploy/kiosk.sh"
