"""macOS `caffeinate` wrapper — keep the Mac awake while sessions run.

One toggle for the rover menu: 'C' flips caffeinate on/off. When on,
a `caffeinate -d -i` process is spawned in the background and survives
rover exits (PID is persisted to ~/.rover/caffeinate.pid so the next
rover launch can see it's still active).

Deliberately narrow:
- No sudo.
- No pmset.
- No schedule / timer logic.
One job: tell the Mac not to sleep so claude keeps processing while
you're away. If you need anything more, use System Settings or
Amphetamine.

Non-macOS hosts: every call is a graceful no-op. `is_available()`
returns False and the menu hides the option.
"""

from __future__ import annotations

import os
import pathlib
import shutil
import signal
import subprocess
import sys


_PID_FILE = pathlib.Path.home() / ".rover" / "caffeinate.pid"


def is_available() -> bool:
    """True only on macOS with the `caffeinate` binary on PATH."""
    if sys.platform != "darwin":
        return False
    return shutil.which("caffeinate") is not None


def _read_pid() -> int | None:
    try:
        raw = _PID_FILE.read_text(encoding="utf-8").strip()
    except (FileNotFoundError, OSError):
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _pid_alive(pid: int) -> bool:
    """True if the process exists and is signalable by this user."""
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False
    except OSError:
        return False


def is_awake() -> bool:
    """True if a caffeinate process started by rover is still running."""
    pid = _read_pid()
    if pid is None:
        return False
    if _pid_alive(pid):
        return True
    # Stale PID file — clean up quietly.
    try:
        _PID_FILE.unlink(missing_ok=True)
    except OSError:
        pass
    return False


def wake() -> bool:
    """Start `caffeinate -d -i` detached. Returns True on success.

    Idempotent: if a caffeinate is already running, returns True without
    starting another one.
    """
    if is_awake():
        return True
    if not is_available():
        return False

    try:
        _PID_FILE.parent.mkdir(parents=True, exist_ok=True)
        proc = subprocess.Popen(
            ["caffeinate", "-d", "-i"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,  # detach so it survives rover exit
        )
        _PID_FILE.write_text(str(proc.pid), encoding="utf-8")
        return True
    except (OSError, subprocess.SubprocessError):
        return False


def sleep() -> bool:
    """Stop the tracked caffeinate process. Returns True on success.

    Idempotent: if no caffeinate is running, returns True.
    """
    pid = _read_pid()
    if pid is None:
        return True

    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        pass  # already gone
    except PermissionError:
        return False
    except OSError:
        return False

    try:
        _PID_FILE.unlink(missing_ok=True)
    except OSError:
        pass
    return True


def toggle() -> bool:
    """Flip the caffeinate state. Returns the new state (True = awake)."""
    if is_awake():
        sleep()
        return False
    return wake()
