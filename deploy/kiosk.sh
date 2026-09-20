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
URL="${FACE_URL:-http://127.0.0.1:$PORT/twinkle}"

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

# Panel fixes go here if the display needs forcing -- see DISPLAY.md.
# xrandr --output DP-1 --mode "1024x600_60.00"
# xrandr --output DP-1 --rotate left

BROWSER=""
for c in chromium chromium-browser google-chrome chrome; do
  if command -v "$c" >/dev/null 2>&1; then BROWSER="$c"; break; fi
done
if [ -z "$BROWSER" ]; then
  echo "no chromium found -- run: sudo apt install -y chromium" >&2
  exit 1
fi

# Chromium remembers that it was killed rather than closed and shows a
# "restore pages?" bubble over the dog's face on every boot. Forget it.
PROF="$HOME/.config/chromium/Default/Preferences"
if [ -f "$PROF" ]; then
  sed -i 's/"exit_type":"Crashed"/"exit_type":"Normal"/; s/"exited_cleanly":false/"exited_cleanly":true/' "$PROF" || true
fi

exec "$BROWSER" \
  --kiosk \
  --noerrdialogs \
  --disable-infobars \
  --disable-session-crashed-bubble \
  --disable-features=TranslateUI \
  --no-first-run \
  --check-for-update-interval=31536000 \
  --password-store=basic \
  --autoplay-policy=no-user-gesture-required \
  "$URL"
