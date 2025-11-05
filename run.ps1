# Windows PowerShell launcher script for TVPlayer
# Automatically finds and uses the virtual environment

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

# Find the main entry point
$mainFile = ""
$possibleEntries = @("tv.py", "TVPlayer.py", "main.py", "app.py")
foreach ($entry in $possibleEntries) {
    $testPath = Join-Path $scriptDir $entry
    if (Test-Path $testPath) {
        $mainFile = $testPath
        break
    }
}

if (-not $mainFile) {
    Write-Host "Error: No entry point found (tried: $($possibleEntries -join ', '))" -ForegroundColor Red
    exit 1
}

# Find Python executable (prefer virtual environment)
$pythonBin = ""
$venvPaths = @(
    (Join-Path $scriptDir ".venv\Scripts\python.exe"),
    (Join-Path $scriptDir "venv\Scripts\python.exe")
)

foreach ($venvPath in $venvPaths) {
    if (Test-Path $venvPath) {
        $pythonBin = $venvPath
        break
    }
}

if (-not $pythonBin) {
    # Fall back to system Python
    $pythonCmd = Get-Command python -ErrorAction SilentlyContinue
    if ($pythonCmd) {
        $pythonBin = $pythonCmd.Path
    } else {
        Write-Host "Error: Python not found. Install Python or run install.ps1 first." -ForegroundColor Red
        exit 1
    }
}

Write-Host "Starting TVPlayer..." -ForegroundColor Green
Write-Host "  Python: $pythonBin"
Write-Host "  Entry: $mainFile"
Write-Host ""

# Run the application
& $pythonBin $mainFile $args
