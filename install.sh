#!/bin/bash
set -e

GREEN="\e[32m"
RESET="\e[0m"
echo "=== TVPlayer Installer (Linux) ==="

# Ensure Python 3 is available
if ! command -v python3 >/dev/null; then
    echo "Python 3 is required. Please install Python 3 and re-run this script."
    exit 1
fi

# Create virtual environment
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi
source venv/bin/activate

# Install Python packages
if [ -z "$SKIP_PIP" ]; then
    echo "Installing Python packages..."
    if pip install -r requirements.txt; then
        pkg_ok=true
    else
        pkg_ok=false
    fi
else
    echo "Skipping Python package installation"
    pkg_ok=true
fi

# Optional: install ffmpeg if missing
if ! command -v ffprobe >/dev/null; then
    echo "ffmpeg/ffprobe not found. The program may use fallback durations."
    if command -v apt-get >/dev/null; then
        read -p "Install ffmpeg using apt-get? [y/N]: " ans
        if [[ "$ans" =~ ^[Yy]$ ]]; then
            sudo apt-get install -y ffmpeg
        fi
    fi
fi

CHANNELS_DIR="$(pwd)/Channels"
echo "Creating folder structure under $CHANNELS_DIR"
mkdir -p "$CHANNELS_DIR/Channel1/Shows" "$CHANNELS_DIR/Channel1/Commercials" "$CHANNELS_DIR/Channel1/Bumpers"
mkdir -p "schedules" "logs"
dir_ok=true

read -p "Enter the path to your media folder to create Channel1 with no commercials (leave blank to skip): " mpath
if [ -n "$mpath" ] && [ -d "$mpath" ]; then
    cp -n "$mpath"/* "$CHANNELS_DIR/Channel1/Shows" 2>/dev/null || true
fi
copy_ok=true

DESKTOP_DIR="${HOME}/Desktop"
mkdir -p "$DESKTOP_DIR"
cat > "$DESKTOP_DIR/TVPlayer.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=TVPlayer
Exec=$(pwd)/venv/bin/python "$(pwd)/tv.py"
Path=$(pwd)
Icon=$(pwd)/logo.png
Terminal=false
EOF
chmod +x "$DESKTOP_DIR/TVPlayer.desktop"

if [ "$pkg_ok" = true ]; then echo -e "${GREEN}[✓] Python packages installed${RESET}"; fi
if [ "$dir_ok" = true ]; then echo -e "${GREEN}[✓] Folder structure created${RESET}"; fi
if [ "$copy_ok" = true ]; then echo -e "${GREEN}[✓] Media setup complete${RESET}"; fi
echo -e "${GREEN}[✓] Installation complete. Run with: $(pwd)/venv/bin/python 'tv.py'${RESET}"
echo "If you have a logo.png file in this directory it will be used for the"
echo "system tray icon on supported desktops."
