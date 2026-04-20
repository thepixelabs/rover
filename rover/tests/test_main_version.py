"""Subprocess smoke tests for `python -m rover --version`.

Verifies:
  1. The command exits with code 0.
  2. The output contains the version declared in rover/__init__.py
     (not a hard-coded literal — that goes stale on every release bump).
"""

from __future__ import annotations

import subprocess
import sys

from rover import __version__


def _run_version() -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "rover", "--version"],
        capture_output=True,
        text=True,
        timeout=10,
    )


def test_version_exits_zero():
    result = _run_version()
    assert result.returncode == 0, (
        f"Expected exit 0, got {result.returncode}.\nstdout={result.stdout}\nstderr={result.stderr}"
    )


def test_version_output_contains_version_string():
    result = _run_version()
    combined = result.stdout + result.stderr
    assert __version__ in combined, (
        f"{__version__!r} not found in output.\n"
        f"stdout={result.stdout}\nstderr={result.stderr}"
    )
