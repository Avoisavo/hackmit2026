#!/bin/sh
# Give another laptop wireless control of the board.
#
#   sh deploy/add-laptop.sh alex@10.254.159.77
#
# Runs from any machine that can already reach the board (over the tunnel with
# BOARD=127.0.0.1, or over USB with adb). Adds that laptop as a tunnel target,
# so the board dials it too. Every listed laptop keeps working at the same time.
#
# THE OTHER LAPTOP MUST FIRST:
#   1. Turn on Remote Login
#        macOS:  System Settings > General > Sharing > Remote Login
#        Linux:  sudo systemctl enable --now ssh
#   2. Join the SAME Wi-Fi as the board.
#   3. Authorise the board's key -- this script prints the exact command.
set -e

TARGET="$1"
[ -n "$TARGET" ] || { echo "usage: sh deploy/add-laptop.sh <user>@<laptop-ip>" >&2; exit 1; }
case "$TARGET" in *@*) ;; *) echo "expected user@ip, got '$TARGET'" >&2; exit 1 ;; esac

CONF=/home/arduino/.sshd/tunnel-target
SSH_PORT="${SSH_PORT:-2222}"

# Prefer the tunnel; fall back to USB.
if ssh -p "$SSH_PORT" -o BatchMode=yes -o ConnectTimeout=6 arduino@::1 true 2>/dev/null; then
  RUN() { ssh -p "$SSH_PORT" -o BatchMode=yes arduino@::1 "$1"; }
  VIA="tunnel"
elif command -v adb >/dev/null 2>&1 && adb devices | sed -n '2p' | grep -q device; then
  RUN() { adb shell "$1"; }
  VIA="usb"
else
  echo "cannot reach the board. start the tunnel, or plug in USB." >&2
  exit 1
fi
echo "reaching the board over $VIA"

RUN "mkdir -p /home/arduino/.sshd; touch $CONF; grep -qxF '$TARGET' $CONF || echo '$TARGET' >> $CONF; sync" >/dev/null
BOARDKEY=$(RUN "cat /home/arduino/.ssh/id_ed25519.pub" | tr -d '\r')
TARGETS=$(RUN "grep -v '^#' $CONF | grep -v '^\$'" | tr -d '\r')

RUN "pkill -f '[r]everse-tunnel' >/dev/null 2>&1; true" >/dev/null 2>&1 || true
sleep 2
RUN "cd /home/arduino/robotdog-face/deploy && nohup setsid ./reverse-tunnel.sh >/tmp/tunnel.log 2>&1 </dev/null & true" >/dev/null 2>&1 || true

cat <<TXT

--------------------------------------------------------------------
added: $TARGET

tunnel targets now:
$TARGETS

TELL THAT PERSON TO RUN THIS ON THEIR LAPTOP, once:

  mkdir -p ~/.ssh && chmod 700 ~/.ssh
  echo '$BOARDKEY' >> ~/.ssh/authorized_keys
  chmod 600 ~/.ssh/authorized_keys

and to turn Remote Login on. Then, with no cable:

  export BOARD=127.0.0.1
  sh deploy/face.sh status
  sh tools/panel.sh

If their laptop IP changes, run this script again with the new address,
and remove the old line from $CONF on the board.
--------------------------------------------------------------------
TXT
