"""Frozen-app entry point for PyInstaller builds.

PyInstaller needs a real script to analyse, and a package run directly as
``__main__`` can't use its own relative imports. This thin launcher imports the
packaged app and hands off to its console entry point.
"""

from chainlinkd.__main__ import main

if __name__ == "__main__":
    main()
