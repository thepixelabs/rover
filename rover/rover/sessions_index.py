"""Cross-account altergo session scanner for rover's yolo-pick flow.

Public API
----------
list_altergo_sessions() -> list[SessionRecord]
    Scan all altergo accounts under ~/.altergo/accounts/ and return all
    discovered sessions sorted most-recent-first.

SessionRecord
    NamedTuple with fields: account, provider, project_path, session_id,
    modified_at (float epoch), preview (str, ≤80 chars of first user turn).

Implementation notes
--------------------
altergo does not yet expose a --recall --json flag, so we fall back to a
direct filesystem scan that mirrors altergo.py's get_sessions() logic:

  ~/.altergo/accounts/<acct>/<dot_dir>/projects/<encoded-path>/<uuid>.jsonl

Provider dot-dirs:
  claude   → .claude/projects/**
  gemini   → .gemini/projects/**
  codex    → .codex/projects/**  (sessions/ is an alias in some versions)
  copilot  → .copilot/projects/**

The encoded project-path directory name uses Claude Code's dash-encoding
convention: -Users-name-Documents-git-foo → /Users/name/Documents/git/foo.
We decode it best-effort via _decode_project_path().

If a session file exists in the *real* home ~/.claude/projects/ (outside any
altergo account) it is attributed to a synthetic account name "native".
"""

from __future__ import annotations

import json
import pathlib
import re
import time
from typing import NamedTuple

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_ALTERGO_DIR = pathlib.Path.home() / ".altergo"
_ACCOUNTS_DIR = _ALTERGO_DIR / "accounts"
_MAIN_CLAUDE = pathlib.Path.home() / ".claude"

# Map provider id → provider dot-dir name and candidate projects subdirs.
# "projects" is the standard Claude Code layout; we also check "sessions"
# as a fallback for providers that may use that name.
_PROVIDER_DIRS: dict[str, tuple[str, list[str]]] = {
    "claude":  (".claude",  ["projects"]),
    "gemini":  (".gemini",  ["projects"]),
    "codex":   (".codex",   ["projects", "sessions"]),
    "copilot": (".copilot", ["projects"]),
}

_MAX_SCAN_LINES = 40   # max lines to read when extracting first user message
_PREVIEW_MAX = 80      # max chars of preview text

# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------

class SessionRecord(NamedTuple):
    account: str       # altergo account name, or "native" for unmanaged home
    provider: str      # "claude" | "gemini" | "codex" | "copilot"
    project_path: str  # decoded project path (best-effort), e.g. /home/user/myproject
    session_id: str    # UUID stem of the .jsonl file
    modified_at: float # st_mtime epoch seconds
    preview: str       # first user message preview (truncated to _PREVIEW_MAX chars)


# ---------------------------------------------------------------------------
# Path helpers (mirrors altergo's decode_project_path)
# ---------------------------------------------------------------------------

def _decode_project_path(encoded: str) -> str:
    """Decode an altergo/Claude Code encoded project directory name.

    -Users-netz-Documents-git-foo  →  /home/user/Documents/git/foo
    """
    if not encoded:
        return ""
    s = encoded
    if s.startswith("-"):
        s = "/" + s[1:].replace("-", "/")
    else:
        s = s.replace("-", "/")
    return s


# ---------------------------------------------------------------------------
# Session file parsing
# ---------------------------------------------------------------------------

_CODE_FENCE_RE = re.compile(r"```[^\n]*\n.*?```", re.DOTALL)
_WS_RE = re.compile(r"\s+")


def _clean(text: str) -> str:
    """Strip code fences and collapse whitespace for a readable preview."""
    text = _CODE_FENCE_RE.sub(" [code] ", text)
    text = _WS_RE.sub(" ", text).strip()
    return text


def _extract_text(content) -> str:
    """Flatten a Claude Code message content field into plain text."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "text" and isinstance(block.get("text"), str):
                parts.append(block["text"])
        return "\n".join(parts)
    return ""


def _is_real_user_message(obj: dict) -> bool:
    """True for genuine human user turns; False for tool_result-only echoes."""
    if obj.get("type") != "user":
        return False
    msg = obj.get("message")
    if not isinstance(msg, dict):
        return False
    content = msg.get("content")
    if isinstance(content, str):
        return bool(content.strip())
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                return bool(block.get("text", "").strip())
    return False


def _scan_session_preview(jsonl_path: pathlib.Path) -> str:
    """Return a short preview string from the first real user message."""
    try:
        with jsonl_path.open("r", encoding="utf-8", errors="replace") as fh:
            for i, raw_line in enumerate(fh):
                if i >= _MAX_SCAN_LINES:
                    break
                raw_line = raw_line.strip()
                if not raw_line:
                    continue
                try:
                    obj = json.loads(raw_line)
                except json.JSONDecodeError:
                    continue
                if _is_real_user_message(obj):
                    text = _extract_text(obj["message"].get("content", ""))
                    cleaned = _clean(text)
                    return cleaned[:_PREVIEW_MAX]
    except OSError:
        pass
    return ""


# ---------------------------------------------------------------------------
# Account metadata
# ---------------------------------------------------------------------------

def _get_account_provider(account_home: pathlib.Path) -> str:
    """Read provider from account.json, fall back to 'claude'."""
    meta_file = account_home / "account.json"
    if meta_file.exists():
        try:
            with meta_file.open("r", encoding="utf-8") as fh:
                data = json.load(fh)
            provider = data.get("provider", "")
            if provider in _PROVIDER_DIRS:
                return provider
        except Exception:
            pass
    # Legacy layout: .claude/ dir present without account.json
    if (account_home / ".claude").is_dir():
        return "claude"
    return "claude"


# ---------------------------------------------------------------------------
# Core scanner
# ---------------------------------------------------------------------------

def _scan_account(
    account_name: str,
    account_home: pathlib.Path,
    provider: str,
) -> list[SessionRecord]:
    """Scan one account's provider dot-dir and return SessionRecord list."""
    records: list[SessionRecord] = []
    dot_dir, project_subdirs = _PROVIDER_DIRS.get(provider, (".claude", ["projects"]))

    for subdir_name in project_subdirs:
        projects_dir = account_home / dot_dir / subdir_name
        if not projects_dir.exists():
            continue

        try:
            for proj_dir in projects_dir.iterdir():
                if not proj_dir.is_dir():
                    continue
                # Skip subagents dirs (Claude Code internal)
                if proj_dir.name == "subagents":
                    continue

                project_path = _decode_project_path(proj_dir.name)

                try:
                    for f in proj_dir.iterdir():
                        if f.suffix != ".jsonl":
                            continue
                        if f.parent.name == "subagents":
                            continue
                        try:
                            st = f.stat()
                        except OSError:
                            continue

                        session_id = f.stem
                        preview = _scan_session_preview(f)
                        records.append(
                            SessionRecord(
                                account=account_name,
                                provider=provider,
                                project_path=project_path,
                                session_id=session_id,
                                modified_at=st.st_mtime,
                                preview=preview,
                            )
                        )
                except OSError:
                    continue
        except OSError:
            continue

    return records


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def list_altergo_sessions() -> list[SessionRecord]:
    """Return all altergo sessions across all accounts, sorted most-recent-first.

    Scans ~/.altergo/accounts/<acct>/ for each account, then also scans the
    native ~/.claude/projects/ directory (attributed to account "native").

    Returns an empty list if no accounts exist or the directory is missing —
    never raises.
    """
    all_records: list[SessionRecord] = []

    # Scan managed altergo accounts
    if _ACCOUNTS_DIR.is_dir():
        try:
            for entry in _ACCOUNTS_DIR.iterdir():
                if not entry.is_dir() or entry.name.startswith("."):
                    continue
                provider = _get_account_provider(entry)
                try:
                    records = _scan_account(entry.name, entry, provider)
                    all_records.extend(records)
                except Exception:
                    continue
        except OSError:
            pass

    # Scan native ~/.claude/projects/ — sessions that live outside any account
    # (e.g. the user's own claude installation at real $HOME).
    native_projects = _MAIN_CLAUDE / "projects"
    if native_projects.is_dir():
        try:
            all_records.extend(_scan_account("native", pathlib.Path.home(), "claude"))
        except Exception:
            pass

    # Global dedup by session_id. Two altergo accounts symlinked to the same
    # provider home (or native + an account sharing an inode) produce
    # duplicates. Precedence: a managed-account record wins over "native",
    # then most-recently-modified wins among ties.
    def _rank(r: SessionRecord) -> tuple[int, float]:
        return (0 if r.account == "native" else 1, r.modified_at)

    best: dict[str, SessionRecord] = {}
    for r in all_records:
        prev = best.get(r.session_id)
        if prev is None or _rank(r) > _rank(prev):
            best[r.session_id] = r
    deduped = list(best.values())

    deduped.sort(key=lambda r: r.modified_at, reverse=True)
    return deduped
