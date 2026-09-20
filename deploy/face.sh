#!/bin/sh
# One command for the whole team. No cable needed once you have SSH access.
#
#   sh deploy/face.sh status              health of the board
#   sh deploy/face.sh deploy              copy the face over and restart it
#   sh deploy/face.sh restart             restart server + kiosk browser
#   sh deploy/face.sh emote Celebrate     drive the face
#   sh deploy/face.sh emotes              list every face name
#   sh deploy/face.sh shell               open a shell on the board
#
# Point it at the board once:
#   export BOARD=10.254.159.201
# Both your laptop and the board must be on the SAME Wi-Fi.
set -e

BOARD="${BOARD:-}"
SSH_PORT="${SSH_PORT:-2222}"
DEST=/home/arduino/robotdog-face
ROOT=$(cd "$(dirname "$0")/.." && pwd)
CMD="${1:-status}"

[ -n "$BOARD" ] || { echo "set the board address first:  export BOARD=<board-ip>" >&2; exit 1; }
# accept-new: a teammate's first connect should not stop on a host-key prompt.
SSH_OPTS="-o ConnectTimeout=8 -o StrictHostKeyChecking=accept-new"
SSH="ssh -p $SSH_PORT $SSH_OPTS arduino@$BOARD"

case "$CMD" in
  status)
    echo "board:  $BOARD"
    curl -s -m 6 "http://$BOARD:8080/health" || echo "face server not answering on port 8080"
    echo
    $SSH 'echo "ssh:    ok"; uptime' 2>/dev/null || echo "ssh:    not reachable on port $SSH_PORT"
    ;;

  deploy)
    echo "== copying the face to $BOARD =="
    # -O uses plain scp rather than sftp; the board's sftp-server may not be enabled.
    for f in server.py README.md \
             web/face.js web/expressive.js web/rabbit.js web/app.js web/index.html web/style.css \
             web/twinkle.js web/twinkle-panel.html web/twinkle-panel.js \
             web/lab.js web/lab.css web/labv2.js web/labv2.css \
             tools/dashboard.html tools/gallery.html tools/lab.html tools/labv2.html \
             tools/rabbit-gallery.html tools/verify-face.cjs tools/verify-twinkle.cjs \
             deploy/kiosk.sh deploy/uploader.py; do
      [ -f "$ROOT/$f" ] || continue
      scp -O -q -P "$SSH_PORT" $SSH_OPTS "$ROOT/$f" "arduino@$BOARD:$DEST/$f" && echo "  ok  $f" || echo "  FAIL $f"
    done
    # This board loses unflushed writes on a reboot or brownout. Always sync,
    # then prove nothing landed empty -- scp reports success either way.
    $SSH "sync; sync; chmod +x $DEST/server.py $DEST/deploy/kiosk.sh; \
          n=\$(find $DEST -type f -size 0 | wc -l); echo \"empty files: \$n\"; [ \$n -eq 0 ]"
    sh "$0" restart
    ;;

  restart)
    # nohup AND setsid, with every stream redirected: without both, sshd kills
    # the new server the moment this command returns and the face goes dark.
    # The wait loops also keep the session open until the process has detached.
    echo "== restarting face on $BOARD =="
    $SSH "
      pkill -f 'robotdog-face/server.py' >/dev/null 2>&1 || true
      sleep 2
      cd $DEST
      nohup setsid env PORT=8080 python3 $DEST/server.py >/tmp/robotdog-face.log 2>&1 </dev/null &
      for i in \$(seq 1 25); do curl -sf http://127.0.0.1:8080/health >/dev/null 2>&1 && break; sleep 1; done
      curl -sf http://127.0.0.1:8080/health >/dev/null 2>&1 || { echo 'server did NOT come up:'; tail -5 /tmp/robotdog-face.log; exit 1; }

      pkill -f '/usr/lib/chromium/chromium' >/dev/null 2>&1 || true
      sleep 3
      nohup setsid env DISPLAY=:0 XAUTHORITY=/home/arduino/.Xauthority PORT=8080 \
        $DEST/deploy/kiosk.sh >/tmp/kiosk.log 2>&1 </dev/null &
      for i in \$(seq 1 25); do [ \"\$(curl -s http://127.0.0.1:8080/health | grep -o '\"faces\": [0-9]*' | tr -dc 0-9)\" -gt 0 ] 2>/dev/null && break; sleep 1; done
      sync
      curl -s http://127.0.0.1:8080/health
    "
    echo
    ;;

  emote)
    [ -n "$2" ] || { echo "usage: sh deploy/face.sh emote <name> [hold-seconds]" >&2; exit 1; }
    curl -s -X POST "http://$BOARD:8080/emote" -d "{\"name\":\"$2\",\"hold\":${3:-0}}"
    echo
    ;;

  emotes)
    curl -s "http://$BOARD:8080/emotes"; echo
    ;;

  shell)
    exec $SSH
    ;;

  *)
    sed -n '2,18p' "$0"
    exit 1
    ;;
esac
