"""tmux session management — list, attach, create, kill."""

from __future__ import annotations

import os
import subprocess
import time
from dataclasses import dataclass


@dataclass
class TmuxSession:
    name: str
    attached: bool       # True if currently attached (someone is viewing it)
    created_epoch: int   # unix timestamp of session creation
    window_count: int    # number of windows in this session

    def age_str(self) -> str:
        """Human-readable age: '4s', '12m', '1h4m', '2d'.

        Age is measured from session creation time to now.  This is a rough
        proxy for "last activity" since tmux does not expose activity time via
        a format specifier that works reliably across versions.
        """
        seconds = max(0, int(time.time()) - self.created_epoch)

        if seconds < 60:
            return f"{seconds}s"

        minutes = seconds // 60
        if minutes < 60:
            return f"{minutes}m"

        hours = minutes // 60
        leftover_minutes = minutes % 60
        if hours < 24:
            if leftover_minutes:
                return f"{hours}h{leftover_minutes}m"
            return f"{hours}h"

        days = hours // 24
        return f"{days}d"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def is_available() -> bool:
    """Return True if the tmux binary is in PATH."""
    try:
        subprocess.run(
            ["tmux", "-V"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=3,
        )
        return True
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return False


def list_sessions() -> list[TmuxSession]:
    """Return all tmux sessions sorted: attached first, then by most recent.

    Uses tmux list-sessions with a tab-separated format so that session names
    containing spaces are still parsed correctly (tmux names cannot contain
    whitespace, but the format string separators must be unambiguous).

    Returns [] if tmux is not running, no sessions exist, or any error occurs.
    """
    fmt = "#{session_name}\t#{session_attached}\t#{session_created}\t#{session_windows}"
    try:
        result = subprocess.run(
            ["tmux", "list-sessions", "-F", fmt],
            capture_output=True,
            text=True,
            timeout=3,
        )
    except FileNotFoundError:
        # tmux not installed
        return []
    except (subprocess.TimeoutExpired, OSError):
        return []

    # Exit code 1 with "no server running" is the normal "nothing to list"
    # case — not an error the caller needs to handle.
    if result.returncode != 0:
        return []

    sessions: list[TmuxSession] = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split("\t")
        if len(parts) != 4:
            continue
        name, attached_raw, created_raw, windows_raw = parts
        try:
            sessions.append(
                TmuxSession(
                    name=name,
                    attached=attached_raw.strip() != "0",
                    created_epoch=int(created_raw.strip()),
                    window_count=int(windows_raw.strip()),
                )
            )
        except ValueError:
            # Malformed line — skip rather than crash
            continue

    # Sort: attached sessions first, then by creation time descending (newest
    # first acts as a proxy for most recently active).
    sessions.sort(key=lambda s: (not s.attached, -s.created_epoch))
    return sessions


def attach_session(name: str) -> None:
    """Attach to a tmux session, blocking until the user detaches.

    Uses subprocess.run (not os.execvp) so that when the user detaches
    (Ctrl+Q / Ctrl+B D), control returns to the caller and the menu loop
    can redisplay — rather than closing the whole SSH session.
    """
    try:
        from rich.console import Console
        Console().print(f"  [bold cyan]\u2192 entering {name}[/bold cyan]  "
                        f"[dim]\u00b7  Ctrl+Q to return to menu[/dim]")
    except Exception:
        print(f"  \u2192 entering {name}  \u00b7  Ctrl+Q to return to menu\n",
              end="", flush=True)

    # tmux 3.6a has a bug where the '=' exact-match prefix fails to resolve
    # targets whose names contain '/'. Plain '-t name' does exact matching
    # anyway for our purposes (tmux does not prefix-match session names),
    # so we use the plain form here.
    subprocess.run(["tmux", "attach-session", "-t", name])


def new_session(
    name: str,
    *,
    cwd: str | None = None,
    cmd: list[str] | None = None,
) -> bool:
    """Create a new detached tmux session.

    Parameters
    ----------
    name:
        Session name (tmux reserves ``:`` and ``.`` in target syntax — avoid
        those in caller-supplied names).
    cwd:
        Working directory for the session (``-c <cwd>``). Inherits caller's
        cwd when None.
    cmd:
        Optional argv to run as the session's initial command. When None
        tmux spawns the user's default shell. When given, passed verbatim
        to execve — no shell quoting needed.

    Returns True on success, False on any failure (name collision, tmux not
    available, etc.).
    """
    argv = ["tmux", "new-session", "-d", "-s", name]
    if cwd:
        argv += ["-c", cwd]
    if cmd:
        argv += ["--", *cmd]
    try:
        result = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return False


def new_attached_session(
    name: str,
    *,
    cwd: str | None = None,
    cmd: list[str] | None = None,
) -> int:
    """Create a tmux session AND attach to it in one atomic call.

    Runs ``tmux new-session -s <name> [-c <cwd>] -- <cmd>`` and blocks until
    the user detaches or the inner command exits. Returns tmux's exit code.

    Why atomic (vs. detached + attach)? Some tmux configs set
    ``destroy-unattached on``, which kills a freshly-detached session in the
    race window before the caller can attach. ``new-session`` (no ``-d``)
    bundles the two so there's no race window.
    """
    argv = ["tmux", "new-session", "-s", name]
    if cwd:
        argv += ["-c", cwd]
    if cmd:
        argv += ["--", *cmd]
    try:
        result = subprocess.run(argv)
        return result.returncode
    except (FileNotFoundError, OSError):
        return 127


def has_session(name: str) -> bool:
    """Return True if a tmux session with this exact name exists.

    Uses plain '-t name' (not '=name'): tmux's '=' exact-match prefix is
    buggy in 3.6a when the name contains '/', and plain -t already does
    exact session-name matching (tmux never prefix-matches session names).
    """
    try:
        result = subprocess.run(
            ["tmux", "has-session", "-t", name],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=3,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return False


def unique_session_name(base: str) -> str:
    """Return a session name that does not collide with any existing session.

    If *base* is free, returns it unchanged. Otherwise appends ``#2``,
    ``#3``, … until a free slot is found. The ``#`` suffix avoids
    visual ambiguity with project names that already contain hyphens.
    """
    try:
        result = subprocess.run(
            ["tmux", "list-sessions", "-F", "#{session_name}"],
            capture_output=True,
            text=True,
            timeout=3,
        )
        existing = set(result.stdout.splitlines()) if result.returncode == 0 else set()
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return base

    if base not in existing:
        return base

    n = 2
    while True:
        candidate = f"{base}#{n}"
        if candidate not in existing:
            return candidate
        n += 1


def kill_session(name: str) -> bool:
    """Kill a named tmux session.

    Returns True on success, False on any failure.
    """
    try:
        result = subprocess.run(
            ["tmux", "kill-session", "-t", name],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return False
