"""Console entry point for Chainlinkd."""

from __future__ import annotations

import argparse

from . import __version__
from .app import ChainlinkdApp


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="chainlinkd",
        description="A terminal habit tracker. Don't break the chain.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"chainlinkd {__version__}",
    )
    parser.parse_args()

    ChainlinkdApp().run()


if __name__ == "__main__":
    main()
