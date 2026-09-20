#!/bin/sh
# Start the unified control plane with this checkout's private provider settings.
set -eu
robot_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
robot_python="${GO2_PYTHON:-$HOME/dimensional-applications/.venv/bin/python}"
exec "$robot_python" -m uvicorn app:app \
  --app-dir "$robot_dir" --env-file "$robot_dir/../.env.local" \
  --host 127.0.0.1 --port 8020 "$@"
