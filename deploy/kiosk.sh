#!/bin/sh
# Brings up the whole face: starts the server if nothing is serving yet, then
# launches the browser fullscreen. Run by the desktop session on login --
# see robotdog-face.desktop.
#
# Deliberately does not depend on systemd. The UNO Q has no user session bus
# until someone logs in, so a systemd --user unit cannot be installed over adb
# on a board that has never had a monitor attached. One script, no services.
set -e

ROOT=$(cd "$(dirname "$0")/.." && pwd)
PORT="${PORT:-8080}"
# The rabbit face is the default display. Set FACE_URL to override, for
# example FACE_URL=http://127.0.0.1:8080/twinkle for the old Twinkle panel.
URL="${FACE_URL:-http://127.0.0.1:$PORT/?bare=1}"

# Key-only sshd for the team, run as this user on a high port. The packaged
# adbd on this board is wired to the USB gadget and cannot listen on TCP, and
# enabling the system sshd needs a root password nobody has. This needs neither.
SSHD_DIR="$HOME/.sshd"
if [ -f "$SSHD_DIR/sshd_config" ] && ! pgrep -f "sshd -f $SSHD_DIR/sshd_config" >/dev/null 2>&1; then
  setsid /usr/sbin/sshd -f "$SSHD_DIR/sshd_config" -E /tmp/sshd.log </dev/null >/dev/null 2>&1 &
fi

# Reverse tunnel out to a laptop, if one is configured. The phone hotspot
# isolates its clients: the board can reach a laptop, but no laptop can reach
# the board. So the board dials out and forwards its own ports back.
# Configure with: echo 'user@laptop-ip' > ~/.sshd/tunnel-target
if [ -f "$HOME/.sshd/tunnel-target" ] && ! pgrep -f "[r]everse-tunnel" >/dev/null 2>&1; then
  setsid "$ROOT/deploy/reverse-tunnel.sh" >/tmp/tunnel.log 2>&1 </dev/null &
fi

health() { curl -sf "http://127.0.0.1:$PORT/health" >/dev/null 2>&1; }

if ! health; then
  PORT="$PORT" setsid nohup python3 "$ROOT/server.py" >/tmp/robotdog-face.log 2>&1 &
fi

i=0
while [ $i -lt 45 ]; do
  health && break
  i=$((i + 1))
  sleep 1
done
if ! health; then
  echo "server never came up -- see /tmp/robotdog-face.log" >&2
  exit 1
fi

# A robot dog whose face goes black after ten minutes is a broken robot dog.
if command -v xset >/dev/null 2>&1; then
  xset s off || true
  xset -dpms || true
  xset s noblank || true
fi
if command -v unclutter >/dev/null 2>&1; then
  unclutter -idle 0 -root &
fi

# The browser is handed to display-watch.sh. X starts before the USB-C dongle is
# detected, so launching chromium here would paint onto a screen that is not
# there yet. The watcher waits for an output to appear, sets its mode, and
# relaunches the face onto it -- and falls back to the virtual screen if the
# board is running with no panel attached.
exec "$ROOT/deploy/display-watch.sh"
