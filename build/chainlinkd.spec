# build/chainlinkd.spec — PyInstaller build specification for Chainlinkd.
#
# Usually invoked through build/build-linux.sh, but you can run it directly
# from the project root:
#
#     uv pip install pyinstaller
#     uv run pyinstaller build/chainlinkd.spec --clean --noconfirm
#
# It produces a onedir bundle at dist/chainlinkd/ whose launcher is
# dist/chainlinkd/chainlinkd. Python, Textual and the packaged schema.sql are
# bundled, so it runs on a machine with no Python installed.

import os

from PyInstaller.utils.hooks import collect_all

# This spec lives in build/, so resolve everything against the project root.
# SPECPATH is injected by PyInstaller and points at this file's directory.
PROJECT_ROOT = os.path.dirname(SPECPATH)


def _root(*parts):
    return os.path.join(PROJECT_ROOT, *parts)


# The domain reads schema.sql via importlib.resources, so it must land inside
# the bundled ``chainlinkd`` package directory.
datas = [(_root("src", "chainlinkd", "schema.sql"), "chainlinkd")]
binaries = []
hiddenimports = []

# Textual (and Rich beneath it) load widgets and CSS/assets lazily, which the
# static analysis can't follow — pull in their submodules and data files.
for package in ("textual", "rich"):
    pkg_datas, pkg_binaries, pkg_hiddenimports = collect_all(package)
    datas += pkg_datas
    binaries += pkg_binaries
    hiddenimports += pkg_hiddenimports

a = Analysis(
    [_root("packaging", "launcher.py")],
    pathex=[_root("src")],  # make the `chainlinkd` package importable
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,  # onedir: binaries/datas are collected below
    name="chainlinkd",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,  # Chainlinkd is a terminal UI, so keep the console attached
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="chainlinkd",
)
