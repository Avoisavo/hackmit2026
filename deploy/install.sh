#!/bin/sh
# Run ON THE UNO Q. Installs the face as a service and makes it start on boot.
#
#   scp -r robotdog-face/ <user>@<board>:~/
#   ssh <user>@<board> 'sudo sh ~/robotdog-face/deploy/install.sh'
set -e

DEST=/opt/robotdog-face
SRC=$(cd "$(dirname "$0")/.." && pwd)

if [ "$(id -u)" -ne 0 ]; then
  echo "run me with sudo" >&2
  exit 1
fi

# The desktop session that will host the browser belongs to the login user,
# not to root, so the autostart entry has to land in their home.
TARGET_USER="${SUDO_USER:-arduino}"
TARGET_HOME=$(getent passwd "$TARGET_USER" | cut -d: -f6)
if [ -z "$TARGET_HOME" ]; then
  echo "could not resolve home for user '$TARGET_USER'" >&2
  exit 1
fi

echo "installing from $SRC to $DEST (desktop user: $TARGET_USER)"

if ! command -v chromium >/dev/null 2>&1 && ! command -v chromium-browser >/dev/null 2>&1; then
  echo "installing chromium..."
  apt-get update -qq && apt-get install -y -qq chromium unclutter || \
    echo "WARNING: chromium install failed -- install it by hand" >&2
fi

mkdir -p "$DEST"
if [ "$SRC" != "$DEST" ]; then
  cp -r "$SRC/server.py" "$SRC/web" "$SRC/tools" "$SRC/deploy" "$DEST/"
fi
chmod +x "$DEST/deploy/kiosk.sh"

install -m 644 "$DEST/deploy/robotdog-face.service" /etc/systemd/system/robotdog-face.service
systemctl daemon-reload
systemctl enable robotdog-face.service
systemctl restart robotdog-face.service

install -d -o "$TARGET_USER" -g "$TARGET_USER" "$TARGET_HOME/.config/autostart"
install -m 644 -o "$TARGET_USER" -g "$TARGET_USER" \
  "$DEST/deploy/robotdog-face.desktop" "$TARGET_HOME/.config/autostart/robotdog-face.desktop"

echo
echo "done. server:"
systemctl --no-pager --lines=3 status robotdog-face.service || true
echo
echo "the face starts with the desktop session -- reboot, or run it now with:"
echo "  $DEST/deploy/kiosk.sh"
echo
echo "test the API from anywhere on the network:"
echo "  curl -X POST http://<board-ip>:8080/emote -d '{\"name\":\"happy\",\"hold\":3}'"
