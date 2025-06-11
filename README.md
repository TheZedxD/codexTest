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
