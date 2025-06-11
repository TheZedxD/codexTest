#!/bin/bash
set -e

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

echo "Installing Python packages..."
pip3 install --user -r requirements.txt

CHANNELS_DIR="$(pwd)/Channels"
echo "Creating folder structure under $CHANNELS_DIR"
mkdir -p "$CHANNELS_DIR/Channel1/Shows" "$CHANNELS_DIR/Channel1/Commercials"
mkdir -p "schedules" "logs"

read -p "Do you have media files to add now? [y/N]: " add
if [[ "$add" =~ ^[Yy]$ ]]; then
    read -p "Path to your video files for Channel1/Shows: " mpath
    if [ -d "$mpath" ]; then
        cp -n "$mpath"/* "$CHANNELS_DIR/Channel1/Shows" 2>/dev/null || true
    else
        echo "Directory not found, skipping copy."
    fi
fi

echo "Installation complete. Run with: python3 'TVPlayer_Complete copy.py'"
