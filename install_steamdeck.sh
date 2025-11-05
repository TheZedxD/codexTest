#!/bin/bash
set -e
echo "=== TVPlayer Installer (Steam Deck / Linux) ==="

# 1) Python 3 check
if ! command -v python3 >/dev/null; then
  echo "Python 3 is required. Install it and re-run."; exit 1
fi

# 2) Create venv (idempotent) and upgrade installer tooling
if [ ! -d ".venv" ]; then python3 -m venv .venv; fi
source .venv/bin/activate
python -m pip install -U pip wheel setuptools

# 3) Install Python deps
echo "Installing Python packages..."
python -m pip install -r requirements.txt

# 4) Check system media deps (SteamOS is Arch-based; don’t auto-modify system)
need_ffmpeg=false; need_gst=false
command -v ffmpeg >/dev/null 2>&1 || need_ffmpeg=true
command -v ffprobe >/dev/null 2>&1 || need_ffmpeg=true
command -v gst-launch-1.0 >/dev/null 2>&1 || need_gst=true

if $need_ffmpeg || $need_gst; then
  echo ""
  echo "[Notice] System media tools are missing. Video playback may fail until installed."
  if command -v pacman >/dev/null 2>&1; then
    cat <<'EOT'
Steam Deck tips (run in Konsole if you want to install system-wide codecs):
  sudo steamos-readonly disable
  sudo pacman-key --init
  sudo pacman-key --populate archlinux
  sudo pacman -Sy --needed ffmpeg gst-plugins-good gst-plugins-bad gst-plugins-ugly gst-libav
(You can also use Discover GUI to install these. Reboot or re-login afterwards.)
EOT
  fi
  echo ""
fi

# 5) App directories (idempotent)
APPDIR="$(pwd)"
mkdir -p "$APPDIR/Channels/Channel1/Shows" "$APPDIR/Channels/Channel1/Commercials" "$APPDIR/Channels/Channel1/Bumpers"
mkdir -p "$APPDIR/schedules" "$APPDIR/logs"

# 6) Optional: copy starter media
read -p "Path to media for Channel1 (blank to skip): " SRC
if [ -n "$SRC" ] && [ -d "$SRC" ]; then
  cp -n "$SRC"/* "$APPDIR/Channels/Channel1/Shows" 2>/dev/null || true
fi

# 7) Make/update run.sh for convenience
cat > "$APPDIR/run.sh" <<'EOS'
#!/usr/bin/env bash
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
PY="$HERE/.venv/bin/python"
if [ ! -x "$PY" ]; then
  echo ".venv Python not found. Run ./install_steamdeck.sh first."; exit 1
fi
# Default to X11 on Desktop Mode; override as needed
export QT_QPA_PLATFORM=${QT_QPA_PLATFORM:-xcb}
cd "$HERE"
exec "$PY" "$HERE/tv.py" "$@"
EOS
chmod +x "$APPDIR/run.sh"

# 8) Desktop launcher (single icon)
DESK="${HOME}/Desktop"
mkdir -p "$DESK"
cat > "${DESK}/TVPlayer.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=TVPlayer (Infinite TV)
Exec=${APPDIR}/run.sh
Path=${APPDIR}
Icon=${APPDIR}/logo.png
Terminal=false
Categories=AudioVideo;Player;
EOF
chmod +x "${DESK}/TVPlayer.desktop"

echo ""
echo "[✓] Install complete."
echo "Launch from Desktop: TVPlayer (Infinite TV), or run: ${APPDIR}/run.sh"
echo "If playback fails, install ffmpeg + GStreamer as noted above, then try again."
