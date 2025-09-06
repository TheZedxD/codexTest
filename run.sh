#!/usr/bin/env bash
set -euo pipefail

export QT_QPA_PLATFORM=xcb
export QT_MEDIA_BACKEND=gstreamer
export GST_PLUGIN_FEATURE_RANK=vaapidecodebin:PRIMARY,vaapidecode:PRIMARY
export PYTHONUNBUFFERED=1

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

MAIN=""
for entry in tv.py TVPlayer.py main.py app.py; do
  if [[ -f "$SCRIPT_DIR/$entry" ]]; then
    MAIN="$SCRIPT_DIR/$entry"
    break
  fi
done

if [[ -z "$MAIN" ]]; then
  echo "No entrypoint found." >&2
  exit 1
fi

PYTHON_BIN=""
if [[ -x "$SCRIPT_DIR/.venv/bin/python" ]]; then
  PYTHON_BIN="$SCRIPT_DIR/.venv/bin/python"
elif [[ -x "$SCRIPT_DIR/venv/bin/python" ]]; then
  PYTHON_BIN="$SCRIPT_DIR/venv/bin/python"
else
  PYTHON_BIN="python3"
fi

exec "$PYTHON_BIN" "$MAIN" "$@"
