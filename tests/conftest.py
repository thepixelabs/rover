"""Shared pytest fixtures for rover tests.

Three fixtures:
  fake_altergo_tree  — a real tmp_path tree + patched Path.home()
  tmp_events_file    — a tmp events.jsonl with patched telemetry constants
  fake_execvp        — records calls to os.execvp and raises SystemExit(0)
"""

from __future__ import annotations

import json
import pytest


# ---------------------------------------------------------------------------
# fake_altergo_tree
# ---------------------------------------------------------------------------

_UUID_1 = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
_UUID_2 = "ffffffff-0000-1111-2222-333333333333"

# One real user message followed by a tool_result echo that should be ignored.
_REAL_USER_LINE = json.dumps({
    "type": "user",
    "message": {
        "content": "Hello, can you help me refactor this module?"
    }
})

_TOOL_RESULT_LINE = json.dumps({
    "type": "user",
    "message": {
        "content": [
            {"type": "tool_result", "tool_use_id": "x", "content": "done"}
        ]
    }
})


@pytest.fixture()
def fake_altergo_tree(tmp_path, monkeypatch):
    """Create a minimal ~/.altergo tree under tmp_path and patch Path.home().

    Layout:
      <tmp>/
        .altergo/accounts/
          acct-alpha/
            account.json          {"provider": "claude"}
            .claude/projects/
              -Users-user-proj-a/
                <uuid-1>.jsonl    (real user message + tool_result line)
          acct-beta/
            .claude/projects/
              -Users-user-proj-b/
                <uuid-2>.jsonl    (empty — yields empty preview)
        .claude/projects/
          -Users-user-proj-a/
            <uuid-1>.jsonl        (symlink duplicate — dedup test)
    """
    # Build acct-alpha
    alpha = tmp_path / ".altergo" / "accounts" / "acct-alpha"
    alpha_proj = alpha / ".claude" / "projects" / "-Users-user-proj-a"
    alpha_proj.mkdir(parents=True)
    (alpha / "account.json").write_text(json.dumps({"provider": "claude"}), encoding="utf-8")
    session_file = alpha_proj / f"{_UUID_1}.jsonl"
    session_file.write_text(_REAL_USER_LINE + "\n" + _TOOL_RESULT_LINE + "\n", encoding="utf-8")

    # Build acct-beta (no account.json → legacy fallback, empty session file)
    beta = tmp_path / ".altergo" / "accounts" / "acct-beta"
    beta_proj = beta / ".claude" / "projects" / "-Users-user-proj-b"
    beta_proj.mkdir(parents=True)
    (beta_proj / f"{_UUID_2}.jsonl").write_text("", encoding="utf-8")

    # Native duplicate (same UUID as acct-alpha — should be deduped)
    native_proj = tmp_path / ".claude" / "projects" / "-Users-user-proj-a"
    native_proj.mkdir(parents=True)
    native_session = native_proj / f"{_UUID_1}.jsonl"
    native_session.write_text(_REAL_USER_LINE + "\n", encoding="utf-8")

    # Patch Path.home() at the module level used by sessions_index
    monkeypatch.setattr(
        "rover.sessions_index.pathlib.Path.home",
        lambda: tmp_path,
    )
    # sessions_index uses module-level constants evaluated at import time,
    # so also patch the constants directly.
    import rover.sessions_index as si
    monkeypatch.setattr(si, "_ALTERGO_DIR", tmp_path / ".altergo")
    monkeypatch.setattr(si, "_ACCOUNTS_DIR", tmp_path / ".altergo" / "accounts")
    monkeypatch.setattr(si, "_MAIN_CLAUDE", tmp_path / ".claude")

    return tmp_path


# ---------------------------------------------------------------------------
# tmp_events_file
# ---------------------------------------------------------------------------

@pytest.fixture()
def tmp_events_file(tmp_path, monkeypatch):
    """Create ~/.rover/events.jsonl under tmp_path and patch telemetry constants.

    Returns the Path to the events.jsonl file so tests can pre-populate it.
    """
    rover_dir = tmp_path / ".rover"
    rover_dir.mkdir(parents=True)
    events_file = rover_dir / "events.jsonl"
    # Don't create the file — let _emit create it (tests that need pre-existing
    # content should write it themselves via the returned path).

    import rover.telemetry as tel
    monkeypatch.setattr(tel, "_ROVER_DIR", rover_dir)
    monkeypatch.setattr(tel, "_EVENTS_FILE", events_file)

    return events_file


# ---------------------------------------------------------------------------
# fake_execvp
# ---------------------------------------------------------------------------

@pytest.fixture()
def fake_execvp(monkeypatch):
    """Replace subprocess.run in altergo_launcher with a recorder that raises SystemExit(0).

    Historically this patched os.execvp; the launcher now uses subprocess.run
    so altergo exits return to the rover menu loop. The fixture still exposes
    the same ``(file, argv)`` tuple shape for backward compatibility with
    existing assertions.
    """
    calls: list[tuple[str, list[str]]] = []

    def _recorder(argv, *_a, **_kw):
        calls.append((argv[0], list(argv)))
        raise SystemExit(0)

    monkeypatch.setattr("rover.altergo_launcher.subprocess.run", _recorder)
    monkeypatch.setattr("rover.altergo_launcher.os.chdir", lambda p: None)

    # Short-circuit the rover-owned tmux wrap so these argv-contract tests
    # capture the altergo invocation, not the tmux wrapper around it. The
    # wrapping logic has its own dedicated test file.
    monkeypatch.setattr("rover.session_manager.is_available", lambda: False)

    return calls
