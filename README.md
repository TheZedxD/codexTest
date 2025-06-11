# Infinite Tv Setup

Infinite Tv is a PyQt based live TV player. Use the installer for your
platform to install dependencies and create the initial folder structure.
The application is tested on both Windows and Linux and should work out of
the box on either system.

## Linux Install

Run the installer from a terminal:

```bash
bash install.sh
```

The script installs Python packages (including `requests`) and creates
`Channels/Channel1/Shows` and `Channels/Channel1/Commercials` along with
`schedules` and `logs`. You may copy your media files during setup when
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
PowerShell. Administrator permissions are not required.

## Running Infinite Tv

After installation launch the player with:

```bash
python "TVPlayer_Complete copy.py"
```

When starting up or reloading schedules the player displays a short loading
overlay while rebuilding the guide so the listings always match what is
actually playing.

The built-in web remote is available on the LAN after startup. Open the
displayed URL in any browser to control playback from another device. Arrow
buttons let you move the on-screen focus without using a mouse and the new
`[ESC] CLOSE` button can dismiss dialogs remotely.

The TV guide now includes a small panel in the top-right corner showing the
current system time and local weather when internet access is available. Click
the panel or the `refresh` link to update the information or view the day's
forecast.

## Troubleshooting

Ensure Python 3 and pip are installed and available in your `PATH`. If the
installers fail to download packages because your system lacks internet
access, install the packages listed in `requirements.txt` manually.
