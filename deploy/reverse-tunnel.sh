#!/bin/sh
# RUNS ON THE BOARD. Holds a reverse SSH tunnel open to each listed laptop.
#
# Why this exists: the phone hotspot isolates its clients. The board can reach a
# laptop, but no laptop can reach the board. So the board dials out and forwards
# its own ports back:
#
#   laptop:2222 -> board:2222   (ssh into the board)
#   laptop:8080 -> board:8080   (the face server and /emote API)
#
# Configure targets, ONE PER LINE, on the board:
#   printf 'sam@10.254.159.62\nalex@10.254.159.77\n' > ~/.sshd/tunnel-target
#
# Every laptop listed gets its own tunnel, so the whole team has access at the
# same time. Each laptop then uses BOARD=127.0.0.1 as usual. Blank lines and
# lines starting with # are ignored.
#
# Started automatically by deploy/kiosk.sh. Reconnects on its own.
set -e

CONF="${TUNNEL_TARGET_FILE:-$HOME/.sshd/tunnel-target}"
SSH_PORT="${SSH_PORT:-2222}"
FACE_PORT="${FACE_PORT:-8080}"

[ -f "$CONF" ] || { echo "no tunnel targets at $CONF -- nothing to do"; exit 0; }

# One background loop per laptop. If a laptop is asleep or gone, only its own
# loop retries; the others keep working.
hold_tunnel() {
  target="$1"
  echo "tunnel -> $target"
  while :; do
    # ExitOnForwardFailure makes ssh fail fast if that laptop still holds a
    # stale forward, so the loop retries instead of sitting on a dead link.
    ssh -N \
        -o ExitOnForwardFailure=yes \
        -o ServerAliveInterval=15 \
        -o ServerAliveCountMax=3 \
        -o StrictHostKeyChecking=accept-new \
        -o BatchMode=yes \
        -o ConnectTimeout=10 \
        -R "$SSH_PORT:localhost:$SSH_PORT" \
        -R "$FACE_PORT:localhost:$FACE_PORT" \
        "$target" || true
    sleep 5
  done
}

COUNT=0
while IFS= read -r line || [ -n "$line" ]; do
  target=$(printf '%s' "$line" | tr -d ' \r\t')
  case "$target" in ''|'#'*) continue ;; esac
  hold_tunnel "$target" &
  COUNT=$((COUNT + 1))
done < "$CONF"

[ "$COUNT" -gt 0 ] || { echo "no usable targets in $CONF"; exit 0; }
echo "holding $COUNT tunnel(s)"
wait
