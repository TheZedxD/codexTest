Write-Host "=== TVPlayer Installer (Windows) ==="

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

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$channels = Join-Path $root 'Channels'
$shows = Join-Path $channels 'Channel1\Shows'
$commercials = Join-Path $channels 'Channel1\Commercials'

New-Item -ItemType Directory -Force -Path $shows | Out-Null
New-Item -ItemType Directory -Force -Path $commercials | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $root 'schedules') | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $root 'logs') | Out-Null

$add = Read-Host 'Do you have media files to add now? (y/N)'
if ($add -match '^[Yy]') {
    $src = Read-Host 'Path to your video files for Channel1\\Shows'
    if (Test-Path $src) {
        Copy-Item "$src\*" $shows -ErrorAction SilentlyContinue
    } else {
        Write-Host 'Directory not found, skipping copy.'
    }
}

Write-Host "Installation complete. Run: python 'TVPlayer_Complete copy.py'"
