#!/bin/sh
# RUNS ON THE BOARD. Holds a reverse SSH tunnel open to a laptop.
#
# Why this exists: the phone hotspot isolates its clients. The board can reach
# the laptop, but the laptop cannot reach the board. So the board dials out and
# forwards its own ports back:
#
#   laptop:2222 -> board:2222   (ssh into the board)
#   laptop:8080 -> board:8080   (the face server and /emote API)
#
# Configure the target once, on the board:
#   echo 'jingyuan@10.254.159.62' > /home/arduino/.sshd/tunnel-target
#
# Started automatically by deploy/kiosk.sh at login. Reconnects on its own.
set -e

CONF="${TUNNEL_TARGET_FILE:-$HOME/.sshd/tunnel-target}"
SSH_PORT="${SSH_PORT:-2222}"
FACE_PORT="${FACE_PORT:-8080}"

[ -f "$CONF" ] || { echo "no tunnel target at $CONF -- nothing to do"; exit 0; }
TARGET=$(tr -d ' \r\n' < "$CONF")
[ -n "$TARGET" ] || { echo "tunnel target file is empty"; exit 0; }

echo "reverse tunnel to $TARGET (ssh $SSH_PORT, face $FACE_PORT)"

while :; do
  # ExitOnForwardFailure makes ssh fail fast if the laptop still holds a stale
  # forward, so the loop retries instead of sitting on a dead connection.
  ssh -N \
      -o ExitOnForwardFailure=yes \
      -o ServerAliveInterval=15 \
      -o ServerAliveCountMax=3 \
      -o StrictHostKeyChecking=accept-new \
      -o BatchMode=yes \
      -o ConnectTimeout=10 \
      -R "$SSH_PORT:localhost:$SSH_PORT" \
      -R "$FACE_PORT:localhost:$FACE_PORT" \
      "$TARGET" || true
  sleep 5
done
