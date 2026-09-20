#!/bin/sh
# RUN ON YOUR MAC. Pushes the face to the board and restarts it.
# Works over USB or over Wi-Fi -- adb does not care which, as long as
# 'adb devices' shows the board.
#
#   sh deploy/push-face.sh                 # push, sync, restart server + kiosk
#   sh deploy/push-face.sh --no-kiosk      # leave the browser alone
#
# Over Wi-Fi, connect first:  adb connect <board-ip>:5555
set -e

DEST=/home/arduino/robotdog-face
ROOT=$(cd "$(dirname "$0")/.." && pwd)
KIOSK=1
[ "$1" = "--no-kiosk" ] && KIOSK=0

FILES="server.py README.md
web/face.js web/expressive.js web/rabbit.js web/app.js web/index.html web/style.css
web/twinkle.js web/twinkle-panel.html web/twinkle-panel.js
web/lab.js web/lab.css web/labv2.js web/labv2.css
tools/dashboard.html tools/gallery.html tools/lab.html tools/labv2.html
tools/rabbit-gallery.html tools/verify-face.cjs tools/verify-twinkle.cjs
deploy/kiosk.sh"

command -v adb >/dev/null 2>&1 || { echo "adb not found: brew install --cask android-platform-tools" >&2; exit 1; }
adb devices | sed -n '2p' | grep -q device || {
  echo "no board. plug in USB, or over Wi-Fi run: adb connect <board-ip>:5555" >&2; exit 1; }

echo "== pushing to $DEST =="
for f in $FILES; do
  [ -f "$ROOT/$f" ] || { echo "  skip (missing): $f"; continue; }
  adb push "$ROOT/$f" "$DEST/$f" >/dev/null 2>&1 && echo "  ok  $f" || echo "  FAIL $f"
done

# The board loses unflushed writes if it reboots or browns out. Always sync,
# then prove the files actually landed -- adb push reports success either way.
echo "== sync =="
adb shell 'sync; sync' >/dev/null 2>&1
adb shell "chmod +x $DEST/server.py $DEST/deploy/kiosk.sh" >/dev/null 2>&1

echo "== verify =="
EMPTY=$(adb shell "find $DEST -type f -size 0 | wc -l" | tr -d '\r ')
[ "$EMPTY" = "0" ] || { echo "  $EMPTY EMPTY FILES on the board -- push again" >&2; exit 1; }
BAD=0
for f in web/rabbit.js server.py web/index.html web/app.js; do
  L=$(md5 -q "$ROOT/$f" 2>/dev/null || md5sum "$ROOT/$f" | cut -d' ' -f1)
  R=$(adb shell "md5sum $DEST/$f" | tr -d '\r' | cut -d' ' -f1)
  [ "$L" = "$R" ] && echo "  match $f" || { echo "  MISMATCH $f" >&2; BAD=1; }
done
[ "$BAD" = "0" ] || exit 1

echo "== restart server =="
PID=$(adb shell 'pgrep -f "robotdog-face/server.py"' | tr -d '\r' | head -1)
[ -n "$PID" ] && adb shell "kill $PID" >/dev/null 2>&1
sleep 2
adb shell "cd $DEST && (PORT=8080 setsid python3 server.py >/tmp/robotdog-face.log 2>&1 </dev/null &)" >/dev/null 2>&1
sleep 3

if [ "$KIOSK" = "1" ]; then
  echo "== restart kiosk browser =="
  adb shell 'pkill -f "/usr/lib/chromium/chromium"' >/dev/null 2>&1 || true
  sleep 3
  adb shell "cd $DEST && (DISPLAY=:0 XAUTHORITY=/home/arduino/.Xauthority PORT=8080 setsid ./deploy/kiosk.sh >/tmp/kiosk.log 2>&1 </dev/null &)" >/dev/null 2>&1
  sleep 10
fi

adb shell 'sync' >/dev/null 2>&1
echo "== health =="
adb shell 'curl -s http://127.0.0.1:8080/health'
echo
