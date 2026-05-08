"""Background lifecycle management for the dispatch HTTP server.

Lets rover start and stop the dispatch server without holding the user on
the foreground log. The server runs detached in its own process group with
stdout/stderr appended to ``~/.rover/dispatch-server.log`` and PID tracked
in ``~/.rover/dispatch-server.pid``.

Stop is intentionally aggressive because Ctrl+C against ``npm run start``
sometimes leaves the tsx child alive on the port:
  1. SIGTERM the recorded PID's process group.
  2. Wait up to 5 s for the port to free.
  3. SIGKILL anything still holding the port (orphans included).
"""

from __future__ import annotations

import os
import pathlib
import signal
import subprocess
import time

from rover.api import check_health


_ROVER_DIR = pathlib.Path.home() / ".rover"
_PID_FILE = _ROVER_DIR / "dispatch-server.pid"
LOG_FILE = _ROVER_DIR / "dispatch-server.log"

# Auto-detect candidates when no `dispatch_repo_path` is set in config.
_DEFAULT_REPO_CANDIDATES = (
    pathlib.Path.home() / "Documents" / "git" / "dispatch",
    pathlib.Path.home() / "dispatch",
    pathlib.Path.home() / "src" / "dispatch",
    pathlib.Path.home() / "code" / "dispatch",
)


# ── Repo discovery ───────────────────────────────────────────────────────────

def _looks_like_repo(p: pathlib.Path) -> bool:
    return (p / "package.json").is_file() and (p / "server" / "index.ts").is_file()


def find_dispatch_repo(config: dict) -> pathlib.Path | None:
    """Resolve the dispatch repo path: config → CWD → known candidates."""
    configured = (config.get("dispatch_repo_path") or "").strip()
    if configured:
        p = pathlib.Path(configured).expanduser()
        if _looks_like_repo(p):
            return p

    cwd = pathlib.Path.cwd()
    if _looks_like_repo(cwd):
        return cwd

    for c in _DEFAULT_REPO_CANDIDATES:
        if _looks_like_repo(c):
            return c

    return None


# ── PID + port helpers ───────────────────────────────────────────────────────

def _read_pid() -> int | None:
    if not _PID_FILE.exists():
        return None
    try:
        return int(_PID_FILE.read_text(encoding="utf-8").strip())
    except (ValueError, OSError):
        return None


def _clear_pid() -> None:
    try:
        _PID_FILE.unlink()
    except OSError:
        pass


def _is_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _find_pids_on_port(port: int) -> list[int]:
    """Return PIDs currently listening on the given TCP port (via lsof)."""
    try:
        result = subprocess.run(
            ["lsof", "-ti", f"tcp:{port}", "-sTCP:LISTEN"],
            capture_output=True,
            text=True,
            timeout=2.0,
        )
    except (FileNotFoundError, subprocess.SubprocessError):
        return []
    if result.returncode not in (0, 1):  # 1 = no matches, normal
        return []
    return [int(x) for x in result.stdout.split() if x.strip().isdigit()]


def _terminate_pid(pid: int, sig: int) -> None:
    """Send `sig` to the process group of `pid`, falling back to the pid itself."""
    try:
        pgid = os.getpgid(pid)
        os.killpg(pgid, sig)
        return
    except (ProcessLookupError, PermissionError, OSError):
        pass
    try:
        os.kill(pid, sig)
    except OSError:
        pass


# ── Public API ───────────────────────────────────────────────────────────────

def server_status(port: int = 4242) -> dict:
    """Return ``{running, pid, healthy}``.

    ``running`` is true if either the PID file points at a live process or
    the HTTP health check succeeds. Stale PID files are cleared as a side
    effect so callers always see truthful state.
    """
    pid = _read_pid()
    if pid is not None and not _is_alive(pid):
        _clear_pid()
        pid = None

    healthy = check_health(port)

    if pid is None:
        # Maybe the user started the server outside of rover — adopt it for
        # display purposes by surfacing the lsof PID.
        port_pids = _find_pids_on_port(port)
        if port_pids:
            pid = port_pids[0]

    return {"running": bool(pid) or healthy, "pid": pid, "healthy": healthy}


def start_server(repo_path: pathlib.Path, port: int = 4242) -> tuple[bool, str]:
    """Spawn ``npm run start`` detached. Returns ``(success, message)``."""
    status = server_status(port)
    if status["running"]:
        return False, f"Server already running (pid {status['pid']})."

    _ROVER_DIR.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env["DISPATCH_PORT"] = str(port)

    log_fd = open(LOG_FILE, "ab")
    try:
        proc = subprocess.Popen(
            ["npm", "run", "start"],
            cwd=str(repo_path),
            stdout=log_fd,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            env=env,
            start_new_session=True,
            close_fds=True,
        )
    except FileNotFoundError:
        log_fd.close()
        return False, "npm not found in PATH."
    except OSError as exc:
        log_fd.close()
        return False, f"Failed to spawn npm: {exc}"
    finally:
        # Popen dup'd the fd; safe to close ours.
        try:
            log_fd.close()
        except OSError:
            pass

    _PID_FILE.write_text(str(proc.pid), encoding="utf-8")

    # Poll for health up to ~15 s. The TS server takes a few seconds to boot.
    for _ in range(30):
        if not _is_alive(proc.pid):
            _clear_pid()
            return False, f"Server exited immediately — see {LOG_FILE}"
        if check_health(port):
            return True, f"Server started (pid {proc.pid})."
        time.sleep(0.5)

    return True, f"Server started (pid {proc.pid}) — still warming up, log: {LOG_FILE}"


def stop_server(port: int = 4242, kill_timeout: float = 5.0) -> tuple[bool, str]:
    """SIGTERM → wait → SIGKILL. Cleans up PID file. Returns ``(success, msg)``."""
    pids: list[int] = []
    pid_from_file = _read_pid()
    if pid_from_file and _is_alive(pid_from_file):
        pids.append(pid_from_file)
    for p in _find_pids_on_port(port):
        if p not in pids:
            pids.append(p)

    if not pids:
        _clear_pid()
        return True, "Server is not running."

    for pid in pids:
        _terminate_pid(pid, signal.SIGTERM)

    deadline = time.time() + kill_timeout
    while time.time() < deadline:
        time.sleep(0.3)
        alive = [p for p in pids if _is_alive(p)]
        port_pids = _find_pids_on_port(port)
        if not alive and not port_pids:
            _clear_pid()
            return True, "Server stopped."

    # Survivors get SIGKILL — combine with any new orphans we discover.
    survivors = list({*pids, *_find_pids_on_port(port)})
    for pid in survivors:
        _terminate_pid(pid, signal.SIGKILL)

    time.sleep(0.5)
    _clear_pid()

    if _find_pids_on_port(port):
        return False, (
            f"Could not free port {port} — run `lsof -i tcp:{port}` and kill manually."
        )
    return True, "Server force-killed."
