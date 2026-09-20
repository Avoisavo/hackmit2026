#!/bin/sh
# Starts the FastAPI control panel on your laptop and opens it.
#
#   sh tools/panel.sh
#
# The panel runs HERE, not on the board. The UNO Q browns out under load, so the
# board only runs the face. Set BOARD_URL if you are not using the tunnel:
#
#   BOARD_URL=http://10.254.159.201:8080 sh tools/panel.sh
set -e

ROOT=$(cd "$(dirname "$0")/.." && pwd)
PORT="${PANEL_PORT:-9000}"
export BOARD_URL="${BOARD_URL:-http://127.0.0.1:8080}"
VENV="$ROOT/.venv"

if [ ! -x "$VENV/bin/uvicorn" ]; then
  echo "setting up the panel (one time)..."
  python3 -m venv "$VENV"
  "$VENV/bin/pip" install -q --upgrade pip
  "$VENV/bin/pip" install -q fastapi uvicorn httpx
fi

echo "board:  $BOARD_URL"
echo "panel:  http://127.0.0.1:$PORT"
echo

# Fail early with a clear message rather than showing a dead panel.
if ! curl -sf -m 5 "$BOARD_URL/health" >/dev/null 2>&1; then
  echo "WARNING: the board is not answering at $BOARD_URL" >&2
  echo "  tunnel down?  check: curl $BOARD_URL/health" >&2
  echo "  on the same Wi-Fi? use BOARD_URL=http://<board-ip>:8080" >&2
  echo
fi

( sleep 2; command -v open >/dev/null 2>&1 && open "http://127.0.0.1:$PORT" ) &

cd "$ROOT"
exec "$VENV/bin/uvicorn" tools.control_panel:app --host 127.0.0.1 --port "$PORT"
