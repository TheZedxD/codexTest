#!/usr/bin/env bash
set -euo pipefail

# log setup
LOG_DIR="logs"
mkdir -p "$LOG_DIR"
TS=$(date +%Y%m%d_%H%M%S)
LOG_FILE="$LOG_DIR/deck_repair_${TS}.log"
exec > >(tee -a "$LOG_FILE") 2>&1

# helper for status table
declare -a STEP_STATUS=()
function add_status {
  STEP_STATUS+=("$1|$2")
}

# detect SteamOS/Arch
if [[ -f /etc/os-release ]]; then
  . /etc/os-release
  OS_OK=false
  if [[ "${ID:-}" == "steamos" || "${ID:-}" == "arch" ]]; then
    OS_OK=true
  elif [[ "${ID_LIKE:-}" == *"arch"* ]]; then
    OS_OK=true
  fi
  if [[ "$OS_OK" != true ]]; then
    echo "Unsupported system: ${ID:-unknown}. This script supports SteamOS or Arch Linux." >&2
    exit 1
  fi
else
  echo "Unable to detect operating system. This script supports SteamOS or Arch Linux." >&2
  exit 1
fi

# optional sudo
SUDO=""
if command -v sudo >/dev/null 2>&1; then
  SUDO="sudo"
fi

# disable read-only if available
if command -v steamos-readonly >/dev/null 2>&1; then
  $SUDO steamos-readonly disable || true
  trap '$SUDO steamos-readonly enable || true' EXIT
fi

# update and install packages
$SUDO pacman -Syu --noconfirm
PKGS=(ffmpeg gstreamer gst-plugins-base gst-plugins-good gst-plugins-bad gst-plugins-ugly gst-libav gst-plugin-pipewire gstreamer-vaapi pipewire qt5-multimedia qt6-multimedia)
$SUDO pacman -S --needed --noconfirm "${PKGS[@]}"

# python venv and requirements
PYTHON_BIN=$(command -v python3 || command -v python)
if [[ -z "$PYTHON_BIN" ]]; then
  echo "Python not found." >&2
  exit 1
fi
"$PYTHON_BIN" -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
if ! grep -qi '^PyQt5' requirements.txt && ! grep -qi '^PyQt6' requirements.txt; then
  echo 'PyQt5' >> requirements.txt
fi
pip install -r requirements.txt

# determine PyQt version
PYQT_VER=5
if grep -qi '^PyQt6' requirements.txt; then
  PYQT_VER=6
fi

# generate run.sh
cat > run.sh <<'RUNEOF'
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
RUNEOF
chmod +x run.sh

# desktop file
APP_NAME="$(basename "$(pwd)")"
DESKTOP_FILE="${HOME}/.local/share/applications/${APP_NAME}.desktop"
mkdir -p "$(dirname "$DESKTOP_FILE")"
cat > "$DESKTOP_FILE" <<DESKEOF
[Desktop Entry]
Type=Application
Name=${APP_NAME}
Exec=$(realpath run.sh)
Icon=applications-multimedia
Terminal=false
Categories=AudioVideo;
DESKEOF

# diagnostics
# 1) which gst-play-1.0 and gst-discoverer-1.0
echo "Diagnostics: checking gst tools"
set +e
which gst-play-1.0 >/dev/null 2>&1
GP_STATUS=$?
which gst-play-1.0 || true
which gst-discoverer-1.0 >/dev/null 2>&1
GD_STATUS=$?
which gst-discoverer-1.0 || true
if [[ $GP_STATUS -eq 0 && $GD_STATUS -eq 0 ]]; then
  add_status "gst-play-1.0 and gst-discoverer-1.0" PASS
else
  add_status "gst-play-1.0 and gst-discoverer-1.0" FAIL
fi

# 2) gst-discoverer-1.0 on sample
DIAG2="SKIP"
if [[ -f assets/sample.mp4 ]]; then
  gst-discoverer-1.0 assets/sample.mp4
  if [[ $? -eq 0 ]]; then
    DIAG2="PASS"
  else
    DIAG2="FAIL"
  fi
else
  echo "assets/sample.mp4 not found, skipping"
fi
add_status "gst-discoverer-1.0 on assets/sample.mp4" "$DIAG2"

# 3) PyQt multimedia import
if [[ $PYQT_VER -eq 6 ]]; then
  python -c "from PyQt6.QtMultimedia import QMediaPlayer; print('Qt ok')"
  PY_STATUS=$?
else
  python -c "from PyQt5.QtMultimedia import QMediaPlayer; print('Qt ok')"
  PY_STATUS=$?
fi
if [[ $PY_STATUS -eq 0 ]]; then
  add_status "PyQt${PYQT_VER} multimedia import" PASS
else
  add_status "PyQt${PYQT_VER} multimedia import" FAIL
fi
set -e

printf '\n%-45s %s\n' "Step" "Result"
for item in "${STEP_STATUS[@]}"; do
  IFS='|' read -r label result <<<"$item"
  printf '%-45s %s\n' "$label" "$result"
fi

read -n1 -r -p "Press any key to exit..." _
