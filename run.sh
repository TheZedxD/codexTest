#!/usr/bin/env bash
set -euo pipefail

# Use X11 by default, allow override
export QT_QPA_PLATFORM=${QT_QPA_PLATFORM:-xcb}

SCRIPT_DIR=$(cd -- "$(dirname -- "$0")" && pwd)

MAIN=""
for c in "TVPlayer_Complete copy.py" "TVPlayer_Complete.py" "TVPlayer.py" "main.py" "app.py"; do
  if [ -f "$SCRIPT_DIR/$c" ]; then
    MAIN="$SCRIPT_DIR/$c"
    break
  fi
done

if [ -z "$MAIN" ]; then
  echo "No entrypoint found." >&2
  exit 1
fi

exec "$SCRIPT_DIR/.venv/bin/python" "$MAIN" "$@"
