"""Console entry point for Chainlinkd."""

from __future__ import annotations

from .app import ChainlinkdApp


def main() -> None:
    ChainlinkdApp().run()


if __name__ == "__main__":
    main()
