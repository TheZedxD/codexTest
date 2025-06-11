# TVPlayer Setup

This project contains a PyQt based TV player. Use the provided installer for
your platform to set up required packages and the initial folder structure.

## Linux

Run the installer from a terminal:

```bash
bash install.sh
```

The script installs Python dependencies, creates `Channels/Channel1/Shows` and
`Channels/Channel1/Commercials` as well as `schedules` and `logs`.
It also offers to copy your media files during setup.

Videos can be organised in subfolders inside the `Shows` or `Commercials`
directories (e.g. `Shows/Season 1`). The player will automatically search these
subfolders for media files.

## Windows

Open PowerShell and execute:

```powershell
powershell -ExecutionPolicy Bypass -File install.ps1
```

The Windows installer performs the same steps as the Linux version.

## Running the Application

After installation launch the player with:

```bash
python "TVPlayer_Complete copy.py"
```

When starting up or reloading schedules the player displays a short loading
overlay while rebuilding the guide so the listings always match what is
actually playing.
