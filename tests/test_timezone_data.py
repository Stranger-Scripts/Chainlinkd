"""Guards the timezone database the package needs at import time.

Windows ships no IANA timezone database. CPython's ``zoneinfo`` searches
``TZPATH`` (a list of POSIX system directories) and only then falls back to the
``tzdata`` PyPI package, so on Windows ``tzdata`` is the *only* source — and
``models.py`` resolves ``ZoneInfo("UTC")`` at module level, which means a
missing database breaks ``import chainlinkd.models`` outright rather than
failing late in some timezone-specific corner.

These tests reproduce that condition on any platform by emptying ``TZPATH``,
so the Linux/macOS suite catches a regression that would otherwise only show
up on a Windows runner (or, worse, in a shipped Windows binary).
"""

import subprocess
import sys

import pytest

# Run each check in a fresh interpreter: ``reset_tzpath`` mutates process-wide
# state and ``chainlinkd.models`` caches ``UTC`` at import, so neither can be
# meaningfully undone inside the test process.
_PROGRAM = """
import zoneinfo
zoneinfo.reset_tzpath([])          # emulate a system with no IANA database
{body}
"""


def _run(body: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-c", _PROGRAM.format(body=body)],
        capture_output=True,
        text=True,
    )


def test_tzdata_is_available_without_system_database():
    """The bundled database alone must satisfy ``zoneinfo``.

    This is the exact failure mode on Windows: without the ``tzdata``
    dependency this raises ``ZoneInfoNotFoundError``.
    """
    result = _run("zoneinfo.ZoneInfo('UTC')")
    if result.returncode != 0:
        pytest.fail(
            "zoneinfo cannot resolve 'UTC' without a system tz database, so "
            "this environment would fail on Windows. Ensure the 'tzdata' "
            "dependency is installed.\n" + result.stderr.strip()
        )


def test_package_imports_without_system_database():
    """``import chainlinkd.models`` must survive having no system tz database."""
    result = _run("import chainlinkd.models; print(chainlinkd.models.UTC.key)")
    assert result.returncode == 0, (
        "importing chainlinkd.models failed with no system tz database:\n"
        + result.stderr.strip()
    )
    assert result.stdout.strip() == "UTC"


def test_named_zones_resolve_without_system_database():
    """Settings offers real IANA zones, so the database must be complete."""
    result = _run(
        "import zoneinfo;"
        "zoneinfo.ZoneInfo('Europe/Berlin');"
        "print(len(zoneinfo.available_timezones()))"
    )
    assert result.returncode == 0, result.stderr.strip()
    assert int(result.stdout.strip()) > 100
