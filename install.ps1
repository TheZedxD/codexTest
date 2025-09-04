Write-Host "=== TVPlayer Installer (Windows) ==="
$green = "`e[32m"
$reset = "`e[0m"

# Ensure Python
$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) {
    Write-Host "Python is required. Please install Python 3 and ensure 'python' is in PATH."
    exit 1
}

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$venvPath = Join-Path $root 'venv'
if (-not (Test-Path $venvPath)) {
    python -m venv $venvPath
}
$venvPython = Join-Path $venvPath 'Scripts\python.exe'

if (-not $env:SKIP_PIP) {
    Write-Host "Installing Python packages..."
    & $venvPython -m pip install -r (Join-Path $root 'requirements.txt')
    $pkgOk = $?
} else {
    Write-Host "Skipping Python package installation"
    $pkgOk = $true
}

$channels = Join-Path $root 'Channels'
$shows = Join-Path $channels 'Channel1\Shows'
$commercials = Join-Path $channels 'Channel1\Commercials'
$bumpers = Join-Path $channels 'Channel1\Bumpers'

$null = New-Item -ItemType Directory -Force -Path $shows
$null = New-Item -ItemType Directory -Force -Path $commercials
$null = New-Item -ItemType Directory -Force -Path $bumpers
$null = New-Item -ItemType Directory -Force -Path (Join-Path $root 'schedules')
$null = New-Item -ItemType Directory -Force -Path (Join-Path $root 'logs')
$dirOk = $true

$src = Read-Host 'Enter path to your media folder for Channel1 (leave blank to skip)'
if ($src) {
    if (Test-Path $src) {
        Copy-Item "$src\*" $shows -ErrorAction SilentlyContinue
    } else {
        Write-Host 'Directory not found. Skipping copy.'
    }
}
$copyOk = $true

$desktop = [Environment]::GetFolderPath('Desktop')
$shortcut = Join-Path $desktop 'TVPlayer.lnk'
$wsh = New-Object -ComObject WScript.Shell
$sc = $wsh.CreateShortcut($shortcut)
$sc.TargetPath = $venvPython
$sc.Arguments = "`"$($root)\tv.py`""
$sc.WorkingDirectory = $root
$iconPath = Join-Path $root 'logo.png'
if (Test-Path $iconPath) { $sc.IconLocation = $iconPath }
$sc.Save()

Write-Host ""
if ($pkgOk) { Write-Host "$green[✓] Python packages installed$reset" }
if ($dirOk) { Write-Host "$green[✓] Folder structure created$reset" }
if ($copyOk) { Write-Host "$green[✓] Media setup complete$reset" }
Write-Host "$green[✓] Installation complete. Run: `$venvPython `"$root\tv.py`"$reset"
Write-Host "If a logo.png file exists in this folder it will become the"
Write-Host "system tray icon when running Infinite Tv."
