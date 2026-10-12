# build/build-windows.ps1
# Build the Windows x86-64 binary. Run from the project root:
#   powershell -ExecutionPolicy Bypass -File build\build-windows.ps1
#
# Assumes you have already done `uv sync` so the venv contains all the
# runtime deps. Installs PyInstaller into the same venv if missing.
#
# PyInstaller does not cross-compile, so this must run on Windows. CI does
# exactly that on a windows-latest runner (.github/workflows/release.yml).

$ErrorActionPreference = "Stop"

# Make sure we are running from the project root (where pyproject.toml lives).
if (-not (Test-Path "pyproject.toml")) {
    Write-Error "error: run this script from the project root"
    exit 1
}

Write-Host "==> Ensuring pyinstaller is installed in the venv"
uv pip install pyinstaller --quiet
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "==> Running PyInstaller"
uv run pyinstaller build\chainlinkd.spec `
    --clean --noconfirm `
    --workpath $env:TEMP\pyinstaller-chainlinkd
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host ""
Write-Host "Done. Binary directory: dist\chainlinkd\"
Write-Host "Run with:  .\dist\chainlinkd\chainlinkd.exe"
