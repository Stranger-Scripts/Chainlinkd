#!/usr/bin/env bash
# build/build-linux.sh
# Build the Linux x86-64 binary. Run from the project root:
#   chmod +x build/build-linux.sh
#   ./build/build-linux.sh
#
# Assumes you have already done `uv sync` so the venv contains all the
# runtime deps. Installs PyInstaller into the same venv if missing.

set -euo pipefail

# Make sure we are running from the project root (where pyproject.toml lives).
if [ ! -f pyproject.toml ]; then
  echo "error: run this script from the project root" >&2
  exit 1
fi

echo "==> Ensuring pyinstaller is installed in the venv"
uv pip install pyinstaller --quiet

echo "==> Running PyInstaller"
uv run pyinstaller build/chainlinkd.spec \
  --clean --noconfirm \
  --workpath /tmp/pyinstaller-chainlinkd

echo ""
echo "Done. Binary directory: dist/chainlinkd/"
echo "Run with:  ./dist/chainlinkd/chainlinkd"
