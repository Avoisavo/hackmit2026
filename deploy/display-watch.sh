#!/bin/sh
# RUNS ON THE BOARD. Watches for a screen and puts the face on it.
#
# The board has one USB-C port. Moving it from a laptop to the powered display
# dongle cuts power, so the board reboots on its own -- no reboot script needed.
# What is NOT automatic is the panel: X starts before the dongle is detected, so
# the face can end up on a screen that is not there. This watches for an output
# to become connected, sets its mode, and relaunches the browser onto it.
#
# Started by deploy/kiosk.sh. Runs forever.
set -e

ROOT=$(cd "$(dirname "$0")/.." && pwd)
PORT="${PORT:-8080}"
URL="${FACE_URL:-http://127.0.0.1:$PORT/?bare=1}"
export DISPLAY="${DISPLAY:-:0}"
export XAUTHORITY="${XAUTHORITY:-$HOME/.Xauthority}"

# -- single instance ---------------------------------------------------------
# Two watchers each launch a browser and kill the other's, forever. On screen
# that is a black/flash/black loop. mkdir is atomic, so only one can win even if
# both start at the same moment. A plain pid FILE is not enough: deleting it by
# hand while a watcher is alive lets a second one start, which is how the loop
# happened.
LOCKDIR="${TMPDIR:-/tmp}/display-watch.lock"
if ! mkdir "$LOCKDIR" 2>/dev/null; then
  OLD=$(cat "$LOCKDIR/pid" 2>/dev/null || true)
  if [ -n "$OLD" ] && kill -0 "$OLD" 2>/dev/null; then
    echo "another watcher is running (pid $OLD) -- exiting"
    exit 0
  fi
  echo "clearing a stale lock from pid ${OLD:-unknown}"
  rm -rf "$LOCKDIR"
  mkdir "$LOCKDIR" 2>/dev/null || { echo "cannot take the lock" >&2; exit 1; }
fi
echo $$ > "$LOCKDIR/pid"
trap 'rm -rf "$LOCKDIR"' EXIT INT TERM
echo "watcher started (pid $$)"

connected_output() {
  xrandr 2>/dev/null | awk '/ connected/{print $1; exit}'
}

browser_bin() {
  for c in chromium chromium-browser google-chrome chrome; do
    command -v "$c" >/dev/null 2>&1 && { echo "$c"; return; }
  done
}

browser_up() { pgrep -f -- "--kiosk" >/dev/null 2>&1; }

# Kill only OUR kiosk browser. A bare "pkill -f chromium" would also take out
# the Arduino App Lab, which the board restarts, adding a second flashing loop.
kill_browsers() {
  for p in $(pgrep -f "/usr/lib/chromium/chromium" 2>/dev/null); do
    [ -r "/proc/$p/cmdline" ] || continue
    tr '\0' ' ' < "/proc/$p/cmdline" 2>/dev/null | grep -q -- "--kiosk" && kill "$p" 2>/dev/null || true
  done
  i=0
  while [ $i -lt 12 ]; do
    browser_up || return 0
    i=$((i + 1)); sleep 1
  done
  for p in $(pgrep -f -- "--kiosk" 2>/dev/null); do kill -9 "$p" 2>/dev/null || true; done
  sleep 2
}

launch_face() {
  out="$1"
  if [ -n "$out" ]; then
    # --auto picks the panel's preferred mode. If your panel needs forcing, see
    # deploy/DISPLAY.md and add an explicit --mode here.
    xrandr --output "$out" --auto --primary 2>/dev/null || true
    [ -n "$FACE_ROTATE" ] && xrandr --output "$out" --rotate "$FACE_ROTATE" 2>/dev/null || true
  fi

  xset s off 2>/dev/null || true
  xset -dpms 2>/dev/null || true
  xset s noblank 2>/dev/null || true

  B=$(browser_bin)
  [ -n "$B" ] || { echo "no chromium found" >&2; return 1; }

  kill_browsers

  # Chromium shows a "restore pages?" bubble over the face after a hard power
  # cut. Forget the crash so the panel shows only the rabbit.
  PROF="$HOME/.config/chromium/Default/Preferences"
  [ -f "$PROF" ] && sed -i 's/"exit_type":"Crashed"/"exit_type":"Normal"/; s/"exited_cleanly":false/"exited_cleanly":true/' "$PROF" 2>/dev/null || true

  setsid "$B" --kiosk --noerrdialogs --disable-infobars \
    --disable-session-crashed-bubble --disable-features=TranslateUI \
    --no-first-run --check-for-update-interval=31536000 \
    --password-store=basic --autoplay-policy=no-user-gesture-required \
    "$URL" >/tmp/face-browser.log 2>&1 </dev/null &
  echo "face launched on ${out:-virtual screen}"
}

wait_for_server() {
  i=0
  while [ $i -lt 60 ]; do
    curl -sf "http://127.0.0.1:$PORT/health" >/dev/null 2>&1 && return 0
    i=$((i + 1)); sleep 1
  done
  return 1
}

LAST=""
HEADLESS=""
WAITED=0
RETRIES=0
while :; do
  OUT=$(connected_output)

  if [ -n "$OUT" ]; then
    WAITED=0
    if [ "$OUT" != "$LAST" ]; then
      echo "display connected: $OUT"
      wait_for_server || echo "server did not answer; launching anyway" >&2
      launch_face "$OUT" && { LAST="$OUT"; HEADLESS=""; RETRIES=0; }
    elif browser_up; then
      RETRIES=0
    else
      # The browser died: a brownout, a crash, or someone closed it. Back off so
      # a browser that cannot survive does not become a flashing loop.
      RETRIES=$((RETRIES + 1))
      if [ $RETRIES -gt 3 ]; then
        echo "browser died $RETRIES times in a row; waiting 60s before trying again"
        sleep 60
      fi
      echo "browser gone; relaunching on $OUT (attempt $RETRIES)"
      wait_for_server || true
      launch_face "$OUT" || true
      sleep 5   # give it time to come up before the next check
    fi
  else
    if [ -n "$LAST" ]; then
      echo "display disconnected"
      LAST=""
    fi
    # No panel attached. Bring the face up on the virtual screen anyway, once,
    # so the SSE link and the /emote API stay live and testable with no monitor.
    if [ -z "$HEADLESS" ]; then
      WAITED=$((WAITED + 3))
      if [ $WAITED -ge 15 ]; then
        wait_for_server || true
        launch_face "" && HEADLESS=1
        WAITED=0
      fi
    fi
  fi
  sleep 3
done
