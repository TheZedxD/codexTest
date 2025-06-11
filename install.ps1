Write-Host "=== TVPlayer Installer (Windows) ==="
$green = "`e[32m"
$reset = "`e[0m"

# Check for Python
$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) {
    Write-Host "Python is required. Please install Python 3 and ensure 'python' is in PATH."
    exit 1
}

# Ensure pip is available
$pip = Get-Command pip -ErrorAction SilentlyContinue
if (-not $pip) {
    Write-Host "pip not found. Attempting to bootstrap via ensurepip..."
    python -m ensurepip --default-pip
}

Write-Host "Installing Python packages..."
pip install -r requirements.txt
$pkgOk = $?

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$channels = Join-Path $root 'Channels'
$shows = Join-Path $channels 'Channel1\Shows'
$commercials = Join-Path $channels 'Channel1\Commercials'

$null = New-Item -ItemType Directory -Force -Path $shows
$null = New-Item -ItemType Directory -Force -Path $commercials
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

Write-Host ""
if ($pkgOk) { Write-Host "$green[✓] Python packages installed$reset" }
if ($dirOk) { Write-Host "$green[✓] Folder structure created$reset" }
if ($copyOk) { Write-Host "$green[✓] Media setup complete$reset" }
Write-Host "$green[✓] Installation complete. Run: python 'TVPlayer_Complete copy.py'$reset"
