"""HTTP client for the dispatch server.

Fetches /api/state, maps the raw JSON into typed Session dataclasses, and
exposes a small public surface:  fetch_state() and check_health().
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional

# ── Constants ──────────────────────────────────────────────────────────────────

_STATE_PATH = "/api/state"
_TIMEOUT = 3.0

# micro_state values that map to each display status
_RUNNING_STATES  = {"thinking", "tool_use", "researching"}
_APPROVAL_STATES = {"approval"}
_WAITING_STATES  = {"waiting"}
_IDLE_STATES     = {"idle"}
_ERROR_STATES    = {"error"}

# Sort priority — lower number floats to the top of the list
_STATUS_ORDER = {
    "RUNNING":  0,
    "APPROVAL": 1,
    "WAITING":  2,
    "IDLE":     3,
    "ERROR":    4,
}


# ── Data model ─────────────────────────────────────────────────────────────────

@dataclass
class Session:
    session_id: str
    project_name: str
    tool: str
    micro_state: str         # raw value from the API
    display_status: str      # derived: RUNNING | WAITING | APPROVAL | IDLE | ERROR
    active_tool: Optional[str]
    prompt_preview: Optional[str]
    started_at: int          # epoch ms
    last_active_at: int      # epoch ms
    cost_usd: float
    turn_count: int
    model: str
    git_branch: Optional[str]
    token_input: int         # raw input tokens
    token_output: int        # raw output tokens
    token_cache_read: int    # cache-read tokens
    token_cache_write: int   # cache-write tokens

    @property
    def total_tokens(self) -> int:
        return self.token_input + self.token_output + self.token_cache_read + self.token_cache_write

    @property
    def age_seconds(self) -> float:
        """Elapsed seconds since the session started."""
        return (time.time() * 1000 - self.started_at) / 1000

    @property
    def idle_seconds(self) -> float:
        """Elapsed seconds since the session was last active."""
        return (time.time() * 1000 - self.last_active_at) / 1000

    def format_age(self) -> str:
        """Human-readable session age: '4s', '12m', '1h4m'."""
        s = int(self.age_seconds)
        if s < 60:
            return f"{s}s"
        elif s < 3600:
            return f"{s // 60}m"
        else:
            return f"{s // 3600}h{(s % 3600) // 60}m"


# ── Internal helpers ───────────────────────────────────────────────────────────

def _derive_display_status(micro_state: str) -> str:
    """Map a raw microState string to a TUI display status label."""
    if micro_state in _RUNNING_STATES:
        return "RUNNING"
    if micro_state in _APPROVAL_STATES:
        return "APPROVAL"
    if micro_state in _WAITING_STATES:
        return "WAITING"
    if micro_state in _ERROR_STATES:
        return "ERROR"
    # idle and any unknown value fall here
    return "IDLE"


def _parse_session(raw: dict) -> Session:
    """Construct a Session from a raw API dict.  Missing optional fields default to None/0."""
    micro_state = str(raw.get("microState") or "idle")
    token_usage = raw.get("tokenUsage") or {}
    return Session(
        session_id      = str(raw.get("sessionId", "")),
        project_name    = str(raw.get("projectName", "")),
        tool            = str(raw.get("tool", "")),
        micro_state     = micro_state,
        display_status  = _derive_display_status(micro_state),
        active_tool     = raw.get("activeToolName") or None,
        prompt_preview  = raw.get("userPromptPreview") or None,
        started_at      = int(raw.get("startedAt") or 0),
        last_active_at  = int(raw.get("lastActiveAt") or 0),
        cost_usd        = float(raw.get("costUsd") or 0.0),
        turn_count      = int(raw.get("turnCount") or 0),
        model           = str(raw.get("model", "")),
        git_branch      = raw.get("gitBranch") or None,
        token_input     = int(token_usage.get("input") or 0),
        token_output    = int(token_usage.get("output") or 0),
        token_cache_read  = int(token_usage.get("cacheRead") or 0),
        token_cache_write = int(token_usage.get("cacheWrite") or 0),
    )


def _sort_key(session: Session) -> int:
    return _STATUS_ORDER.get(session.display_status, 99)


# ── Public API ─────────────────────────────────────────────────────────────────

def fetch_state(port: int = 4242, hours: float = 2.0) -> tuple[list[Session], bool]:
    """Fetch recent sessions from the dispatch API.

    Returns ``(sessions, server_online)``.

    Sessions are filtered to those whose ``lastActiveAt`` falls within the
    last ``hours`` hours, then sorted: RUNNING first, then APPROVAL, WAITING,
    IDLE, ERROR.

    Returns ``([], False)`` if the server is unreachable or returns an error.
    """
    try:
        import httpx  # deferred so the module imports even without httpx installed
    except ImportError:
        return [], False

    url = f"http://127.0.0.1:{port}{_STATE_PATH}"
    cutoff_ms = (time.time() - hours * 3600) * 1000

    try:
        response = httpx.get(url, timeout=_TIMEOUT)
        response.raise_for_status()
        payload = response.json()
    except Exception:
        return [], False

    raw_sessions = payload.get("sessions")
    if not isinstance(raw_sessions, list):
        # Unexpected payload shape — treat as empty but server is online
        return [], True

    sessions: list[Session] = []
    for raw in raw_sessions:
        if not isinstance(raw, dict):
            continue
        try:
            session = _parse_session(raw)
        except Exception:
            # Malformed individual entry — skip rather than crashing the whole fetch
            continue

        if session.last_active_at >= cutoff_ms:
            sessions.append(session)

    sessions.sort(key=_sort_key)
    return sessions, True


@dataclass
class MenuStats:
    """Aggregated stats for display in the rover menu header."""
    server_online: bool
    agent_count: int          # sessions active in the last hour
    running_count: int        # sessions currently RUNNING
    total_tokens: int         # sum of all token types across all providers
    total_cost_usd: float     # sum of costUsd across all sessions
    tokens_by_provider: dict  # {tool_name: token_count}


def fetch_menu_stats(port: int = 4242, hours: float = 1.0) -> MenuStats:
    """Fetch aggregated stats for the rover menu.

    Uses a 1-second timeout so the menu never hangs.  Falls back to zeroed
    stats if the server is unreachable.
    """
    try:
        import httpx
    except ImportError:
        return MenuStats(False, 0, 0, 0, 0.0, {})

    url = f"http://127.0.0.1:{port}{_STATE_PATH}"
    cutoff_ms = (time.time() - hours * 3600) * 1000

    try:
        response = httpx.get(url, timeout=1.0)
        response.raise_for_status()
        payload = response.json()
    except Exception:
        return MenuStats(False, 0, 0, 0, 0.0, {})

    raw_sessions = payload.get("sessions")
    if not isinstance(raw_sessions, list):
        return MenuStats(True, 0, 0, 0, 0.0, {})

    agent_count = 0
    running_count = 0
    total_tokens = 0
    total_cost = 0.0
    tokens_by_provider: dict[str, int] = {}

    for raw in raw_sessions:
        if not isinstance(raw, dict):
            continue
        try:
            s = _parse_session(raw)
        except Exception:
            continue
        if s.last_active_at < cutoff_ms:
            continue
        agent_count += 1
        if s.display_status == "RUNNING":
            running_count += 1
        t = s.total_tokens
        total_tokens += t
        total_cost += s.cost_usd
        provider = s.tool or "unknown"
        tokens_by_provider[provider] = tokens_by_provider.get(provider, 0) + t

    return MenuStats(
        server_online=True,
        agent_count=agent_count,
        running_count=running_count,
        total_tokens=total_tokens,
        total_cost_usd=total_cost,
        tokens_by_provider=tokens_by_provider,
    )


def check_health(port: int = 4242) -> bool:
    """Return True if the dispatch server is responding."""
    try:
        import httpx
    except ImportError:
        return False

    url = f"http://127.0.0.1:{port}{_STATE_PATH}"
    try:
        response = httpx.get(url, timeout=_TIMEOUT)
        response.raise_for_status()
        return True
    except Exception:
        return False
