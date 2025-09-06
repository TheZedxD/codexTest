#!/usr/bin/env bash
set -euo pipefail

export QT_QPA_PLATFORM=xcb
if [[ "${XDG_SESSION_TYPE:-}" == "wayland" ]]; then
  echo "Warning: XDG_SESSION_TYPE=wayland detected; forcing QT_QPA_PLATFORM=xcb" >&2
fi
export QT_MEDIA_BACKEND=gstreamer
export GST_PLUGIN_FEATURE_RANK=vaapidecodebin:PRIMARY,vaapidecode:PRIMARY

GST_LIB_PATHS=(/usr/lib/x86_64-linux-gnu/gstreamer-1.0 /usr/lib/gstreamer-1.0)
for dir in "${GST_LIB_PATHS[@]}"; do
  if [[ -d "$dir" && ":${LD_LIBRARY_PATH:-}:" != *":$dir:"* ]]; then
    LD_LIBRARY_PATH="${LD_LIBRARY_PATH:+$LD_LIBRARY_PATH:}$dir"
  fi
done
export LD_LIBRARY_PATH

export PYTHONUNBUFFERED=1

echo "Environment:"
echo "  QT_QPA_PLATFORM=$QT_QPA_PLATFORM"
echo "  QT_MEDIA_BACKEND=$QT_MEDIA_BACKEND"
echo "  GST_PLUGIN_FEATURE_RANK=$GST_PLUGIN_FEATURE_RANK"
echo "  LD_LIBRARY_PATH=${LD_LIBRARY_PATH:-}"

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
