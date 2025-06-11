# Infinite Tv Setup

Infinite Tv is a PyQt based live TV player. Use the installer for your
platform to install dependencies and create the initial folder structure.

## Linux Install

Run the installer from a terminal:

```bash
bash install.sh
```

The script installs Python packages and creates `Channels/Channel1/Shows` and
`Channels/Channel1/Commercials` along with `schedules` and `logs`. You may copy
your media files during setup when prompted.

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
displayed URL in any browser to control playback from another device.
