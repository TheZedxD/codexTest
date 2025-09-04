#!/usr/bin/env bash
# PieInstall.sh — Raspberry Pi 4 (Raspberry Pi OS Bookworm)
set -euo pipefail

# ---------- 0) Pre-checks ----------
if ! command -v apt >/dev/null; then
  echo "This script targets Raspberry Pi OS / Debian with apt." >&2
  exit 1
fi

REPO_URL_DEFAULT="https://github.com/TheZedxD/codextest.git"
REPO_DIR_DEFAULT="codextest"

# If not already inside a repo folder, optionally clone fresh
if [ ! -f "requirements.txt" ] && [ ! -f "TVPlayer_Complete.py" ] && [ ! -f "TVPlayer_Complete copy.py" ]; then
  echo "Repo files not found here. Cloning fresh."
  REPO_URL="${1:-$REPO_URL_DEFAULT}"
  REPO_DIR="${2:-$REPO_DIR_DEFAULT}"
  rm -rf "$REPO_DIR"
  git clone "$REPO_URL" "$REPO_DIR"
  cd "$REPO_DIR"
fi

# ---------- 1) System deps (Qt, GStreamer, tools) ----------
echo "[1/6] Installing system packages…"
sudo apt update
sudo apt install -y \
  python3 python3-venv python3-pip python3-dev build-essential git \
  python3-pyqt5 python3-pyqt5.qtmultimedia libqt5multimedia5-plugins \
  gstreamer1.0-plugins-base gstreamer1.0-plugins-good \
  gstreamer1.0-plugins-bad gstreamer1.0-plugins-ugly gstreamer1.0-libav \
  gstreamer1.0-pulseaudio libpulse-mainloop-glib0 \
  qtwayland5 libxkbcommon-x11-0 libxcb-xinerama0 \
  ffmpeg

# ---------- 2) Python venv sharing system PyQt ----------
echo "[2/6] Creating venv (system-site-packages)…"
if [ ! -d ".venv" ]; then
  python3 -m venv .venv --system-site-packages
fi
VENV_PY="./.venv/bin/python"
VENV_PIP="./.venv/bin/pip"
"$VENV_PY" -m pip install -U pip wheel setuptools
# Prefer piwheels for faster ARM wheels (safe for non-Qt deps)
export PIP_INDEX_URL="${PIP_INDEX_URL:-https://www.piwheels.org/simple}"

# ---------- 3) Install Python deps (exclude any Qt bindings) ----------
echo "[3/6] Installing Python requirements (excluding Qt)…"
REQ_SRC="requirements.txt"
REQ_CLEAN="req.noqt.txt"
if [ -f "$REQ_SRC" ]; then
  awk 'BEGIN{IGNORECASE=1}
       !($0 ~ /^pyqt/ || $0 ~ /pyqt5/ || $0 ~ /pyqt6/ || $0 ~ /pyside/ || $0 ~ /qt6?/) {print}' \
       "$REQ_SRC" > "$REQ_CLEAN"
  if [ -s "$REQ_CLEAN" ]; then
    "$VENV_PIP" install -r "$REQ_CLEAN"
  else
    echo "No non-Qt Python deps to install."
  fi
else
  echo "requirements.txt not found. Skipping pip installs."
fi

# ---------- 4) Create runtime folders ----------
echo "[4/6] Creating runtime folders…"
mkdir -p \
  cache caches tmp temp logs data assets media downloads \
  config configs schedules channels images icons thumbnails

# ---------- 5) Sanity check QtMultimedia ----------
echo "[5/6] Verifying QtMultimedia import…"
"$VENV_PY" - <<'PY'
import sys
try:
    from PyQt5.QtMultimedia import QMediaPlayer  # noqa
    from PyQt5.QtMultimediaWidgets import QVideoWidget  # noqa
    print("QtMultimedia import OK:", sys.executable)
except Exception as e:
    print("QtMultimedia import FAILED:", e)
    sys.exit(1)
PY

# ---------- 6) Create launcher scripts and desktop entry ----------
echo "[6/6] Writing run.sh and desktop shortcut…"

# Pick main entrypoint
pick_main() {
  for c in \
    "TVPlayer_Complete copy.py" \
    "TVPlayer_Complete.py" \
    "TVPlayer.py" \
    "main.py" \
    "app.py"
  do
    [ -f "$c" ] && { echo "$c"; return; }
  done
  # Fallback to first file with __main__
  local match
  match=$(grep -rl --include="*.py" -m1 "__main__" . || true)
  [ -n "$match" ] && echo "$match" || echo ""
}

MAIN_FILE=$(pick_main)
if [ -z "$MAIN_FILE" ]; then
  echo "Warning: no entrypoint found. Set MAIN_FILE in run.sh manually." >&2
fi

cat > run.sh <<'RUN'
#!/usr/bin/env bash
set -euo pipefail

# Choose platform plugin if needed
# export QT_QPA_PLATFORM=wayland
export QT_QPA_PLATFORM=${QT_QPA_PLATFORM:-xcb}

# Find main file if not set
MAIN="${MAIN_FILE_PLACEHOLDER}"
if [ ! -f "$MAIN" ]; then
  for c in "TVPlayer_Complete copy.py" "TVPlayer_Complete.py" "TVPlayer.py" "main.py" "app.py"; do
    [ -f "$c" ] && MAIN="$c" && break
  done
fi
[ -z "${MAIN:-}" ] && { echo "No entrypoint found."; exit 1; }

exec "./.venv/bin/python" "$MAIN" "$@"
RUN
sed -i "s|MAIN_FILE_PLACEHOLDER|$MAIN_FILE|g" run.sh
chmod +x run.sh

# Desktop shortcut
DESKTOP_DIR="$HOME/Desktop"
mkdir -p "$DESKTOP_DIR"
APP_NAME="CodeXTest TVPlayer"
cat > "$DESKTOP_DIR/CodeXTest.desktop" <<DESK
[Desktop Entry]
Type=Application
Name=${APP_NAME}
Comment=Launch CodeXTest TV Player
Exec=$(pwd)/run.sh
Icon=utilities-terminal
Terminal=false
Categories=AudioVideo;Player;
DESK
chmod +x "$DESKTOP_DIR/CodeXTest.desktop"

echo
echo "=============================="
echo "Install complete."
echo
echo "Run the app:"
echo "  ./run.sh"
echo
echo "If a Qt platform error appears, try:"
echo "  QT_QPA_PLATFORM=wayland ./run.sh     # Wayland"
echo "  QT_QPA_PLATFORM=xcb ./run.sh         # X11"
echo
echo "If media fails to play, confirm GStreamer packs are installed (already handled)."
echo "Log file not created by default; run as: bash -exo pipefail PieInstall.sh |& tee install.log"
echo "=============================="
