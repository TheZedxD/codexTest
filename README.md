# Infinite Tv Setup

Infinite Tv is a PyQt based live TV player. Use the installer for your
platform to install dependencies and create the initial folder structure.
The application is tested on both Windows and Linux and should work out of
the box on either system.

## Prerequisites

* **Python 3.10+** – ensure `python3` is in your `PATH`
* **pip** – Python package installer
* **ffmpeg** *(optional)* – used for accurate media durations
* **Git** *(optional but recommended)* – for updating the code
* **Visual Studio Code** – editor with the **Python** extension installed

On Linux install these via your package manager. On Windows download the
latest releases from their official websites and check the option to add
Python and Git to your system `PATH`.

## Steam Deck (Desktop Mode)

Prereqs: Python 3 (preinstalled), network, your media files.

Install (one shot):

```bash
cd ~/Desktop/TVPlayer   # or wherever you extracted
chmod +x install_steamdeck.sh
./install_steamdeck.sh
```

Launch: double-click **TVPlayer (Infinite TV)** on Desktop, or `./run.sh`.

If video won't play: install system codecs (ffmpeg, GStreamer good/bad/ugly/libav) via Discover or Konsole commands:

```bash
sudo pacman -S ffmpeg
sudo pacman -S gstreamer gst-plugins-good
sudo pacman -S gst-plugins-bad gst-plugins-ugly
sudo pacman -S gst-libav
```

Logs: see `logs/errors.log` for crashes.

Media folders: add files to `Channels/Channel1/Shows` to start.

**Gaming Mode (optional):**

Add `run.sh` as a Non-Steam Game.

In Launch Options, set: `QT_QPA_PLATFORM=xcb %command%`

UI/tray is best in Desktop Mode.

## Linux Install

Run the installer from a terminal:

```bash
bash install.sh
```

The script installs Python packages (including `requests`) and creates
`Channels/Channel1/Shows`, `Channels/Channel1/Commercials` and
`Channels/Channel1/Bumpers` along with `schedules` and `logs`. You may copy
your media files during setup when
prompted.

Videos can be organised in subfolders inside the `Shows` or `Commercials`
directories (e.g. `Shows/Season 1`). The player will automatically search these
subfolders for media files.

## Windows Install

Open PowerShell and execute:

```powershell
powershell -ExecutionPolicy Bypass -File install.ps1
```

The Windows installer performs the same steps as the Linux script and works in
PowerShell. A `Bumpers` folder is also created for optional channel branding
clips. Administrator permissions are not required.

## Working in Visual Studio Code

1. **Open the folder** – Launch VS Code and choose **File → Open Folder...**
   to select the repository directory.
2. **Install the Python extension** – If prompted, allow VS Code to install the
   recommended extension which provides linting and debugging features.
3. **Select the interpreter** – Press `Ctrl+Shift+P` and run `Python: Select
   Interpreter`. Choose your Python 3 installation.
4. **Install dependencies** – Open the integrated terminal (`Terminal → New
   Terminal`) and run the installer for your platform (`bash install.sh` on
   Linux or `powershell -ExecutionPolicy Bypass -File install.ps1` on Windows).
5. **Run the program** – Use the terminal to execute `python tv.py` or press <kbd>F5</kbd> to start a debug session.

## Running Infinite Tv

After installation launch the player with:

```bash
python tv.py
```

The application minimizes to the system tray while running. If a `logo.png`
image is present in the program directory it will be used as the tray icon on
both Windows and Linux. Right-click the icon for quick channel selection,
access to preferences, or to exit the program. Closing the window simply hides
it in the tray; use **Exit** from the tray menu to quit. Preferences and hotkey
configuration are available from the consolidated **Menu** in the main window
as well as from the tray icon.

When starting up or reloading schedules the player displays a short loading
overlay while rebuilding the guide so the listings always match what is
actually playing. Bumper clips placed in the `Bumpers` folders will play before
and after each commercial break when enabled in Settings.

The built-in web remote is available on the LAN after startup. Open the
displayed URL in any browser to control playback from another device. Arrow
buttons let you move the on-screen focus without using a mouse and the new
`[ESC] CLOSE` button can dismiss dialogs remotely.

The TV guide now includes a small panel in the top-right corner showing the
current system time and local weather when internet access is available. Click
the panel or the `refresh` link to update the information or view the day's
forecast. Use the **Settings** menu to set your preferred weather location.

## Updating Infinite Tv

If you obtained the program from a Git repository you can update it by pulling
the latest changes:

```bash
git pull
```

After updating re-run the installer to fetch any new Python packages:

```bash
bash install.sh     # or install.ps1 on Windows
```

Your existing channel folders and configuration files will be preserved.

## Troubleshooting

Ensure Python 3 and pip are installed and available in your `PATH`. If the
installers fail to download packages because your system lacks internet
access, install the packages listed in `requirements.txt` manually.
