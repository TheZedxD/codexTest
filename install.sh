#!/bin/bash
set -e

GREEN="\e[32m"
RESET="\e[0m"
echo "=== TVPlayer Installer (Linux) ==="

# Check for Python 3
if ! command -v python3 >/dev/null; then
    echo "Python 3 is required. Please install Python 3 and re-run this script."
    exit 1
fi

# Check for pip
if ! command -v pip3 >/dev/null; then
    echo "pip3 not found. Attempting to install..."
    if command -v apt-get >/dev/null; then
        sudo apt-get update
        sudo apt-get install -y python3-pip
    else
        echo "Please install pip for Python 3 manually."
        exit 1
    fi
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

echo "Installing Python packages (PyQt5, Flask, psutil, requests)..."
if pip3 install --user -r requirements.txt; then
    pkg_ok=true
else
    pkg_ok=false
fi

CHANNELS_DIR="$(pwd)/Channels"
echo "Creating folder structure under $CHANNELS_DIR"
mkdir -p "$CHANNELS_DIR/Channel1/Shows" "$CHANNELS_DIR/Channel1/Commercials"
mkdir -p "schedules" "logs"
dir_ok=true

read -p "Enter the path to your media folder to create Channel1 with no commercials (leave blank to skip): " mpath
if [ -n "$mpath" ] && [ -d "$mpath" ]; then
    cp -n "$mpath"/* "$CHANNELS_DIR/Channel1/Shows" 2>/dev/null || true
fi
copy_ok=true

echo
if [ "$pkg_ok" = true ]; then echo -e "${GREEN}[✓] Python packages installed${RESET}"; fi
if [ "$dir_ok" = true ]; then echo -e "${GREEN}[✓] Folder structure created${RESET}"; fi
if [ "$copy_ok" = true ]; then echo -e "${GREEN}[✓] Media setup complete${RESET}"; fi
echo -e "${GREEN}[✓] Installation complete. Run with: python3 'TVPlayer_Complete copy.py'${RESET}"
echo "If you have a logo.png file in this directory it will be used for the"
echo "system tray icon on supported desktops."
