# Build script for Scraper Web V2 (PowerShell)
# Usage: Open PowerShell as normal user in project folder and run: .\build.ps1

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

Write-Host "Starting build for Scraper Web V2"

# Ensure Python is available
try {
    $py = (Get-Command python -ErrorAction Stop).Source
    Write-Host "Using Python: $py"
} catch {
    Write-Error "Python not found in PATH. Install Python 3.10+ and re-run."
    exit 1
}

# Create venv if missing
if (-not (Test-Path .\venv)) {
    Write-Host "Creating virtual environment..."
    python -m venv venv
}

# Activate venv for this session
Write-Host "Activating virtual environment..."
. .\venv\Scripts\Activate.ps1

Write-Host "Upgrading pip..."
python -m pip install --upgrade pip

# Install requirements (this can take time)
Write-Host "Installing requirements from requirements.txt..."
python -m pip install -r requirements.txt

# Ensure playwright browsers are installed
Write-Host "Installing Playwright browsers (this will download browser binaries)..."
try {
    python -m playwright install
} catch {
    Write-Warning "Playwright install failed or not needed. Ensure Playwright is installed and run 'python -m playwright install' manually if required."
}

# Run PyInstaller with spec
Write-Host "Running PyInstaller with spec..."
# Ensure pyinstaller is available
python -m pip install --upgrade pyinstaller | Out-Null
pyinstaller ScraperWEB.spec --noconfirm

if (Test-Path .\dist) {
    Write-Host "Build finished. Check the 'dist' directory for the executable."
    Get-ChildItem .\dist -Recurse | Select-Object FullName, Length
} else {
    Write-Error "Build did not produce a 'dist' directory. Check the output above for errors."
    exit 1
}

Write-Host "Done."
