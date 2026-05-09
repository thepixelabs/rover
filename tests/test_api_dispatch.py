"""Tests for rover.api — dispatch HTTP client layer.

Covers:
  - Session dataclass properties (age_seconds, idle_seconds, format_age,
    total_tokens)
  - _derive_display_status mapping
  - _parse_session correctly maps raw dict fields
  - fetch_state returns ([], False) on network error
  - fetch_state filters by cutoff and sorts by priority
  - fetch_state handles malformed entries gracefully
  - fetch_activity parses ActivityEvent fields
  - fetch_activity returns ([], False) on error
  - fetch_single_session finds session by ID
  - fetch_single_session returns (None, True) when ID absent
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest

from rover.api import (
    _derive_display_status,
    _parse_activity_event,
    _parse_session,
    fetch_activity,
    fetch_single_session,
    fetch_state,
)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_raw_session(**overrides) -> dict:
    base = {
        "sessionId": "sess-abc",
        "projectName": "my-proj",
        "tool": "claude",
        "microState": "thinking",
        "activeToolName": None,
        "userPromptPreview": "refactor the auth module",
        "startedAt": int(time.time() * 1000) - 60_000,
        "lastActiveAt": int(time.time() * 1000) - 5_000,
        "costUsd": 0.0123,
        "turnCount": 3,
        "model": "claude-sonnet-4-6",
        "gitBranch": "feat/auth",
        "tokenUsage": {
            "input": 1000,
            "output": 500,
            "cacheRead": 200,
            "cacheWrite": 100,
        },
    }
    base.update(overrides)
    return base


def _make_raw_activity(**overrides) -> dict:
    base = {
        "id": "evt-uuid-001",
        "timestamp": int(time.time() * 1000) - 10_000,
        "type": "phase_hint",
        "projectName": "my-proj",
        "projectPath": "/home/user/my-proj",
        "epicName": "auth-refactor",
        "epicTitle": "Auth Refactor",
        "sessionId": "sess-abc",
        "agentName": "staff-engineer",
        "phaseId": "1",
    }
    base.update(overrides)
    return base


# ── _derive_display_status ─────────────────────────────────────────────────────

class TestDeriveDisplayStatus:
    @pytest.mark.parametrize("micro_state,expected", [
        ("thinking",   "RUNNING"),
        ("tool_use",   "RUNNING"),
        ("researching","RUNNING"),
        ("approval",   "APPROVAL"),
        ("waiting",    "WAITING"),
        ("error",      "ERROR"),
        ("idle",       "IDLE"),
        ("unknown_xyz","IDLE"),
        ("",           "IDLE"),
    ])
    def test_mapping(self, micro_state: str, expected: str) -> None:
        assert _derive_display_status(micro_state) == expected


# ── _parse_session ─────────────────────────────────────────────────────────────

class TestParseSession:
    def test_basic_fields(self) -> None:
        raw = _make_raw_session()
        s = _parse_session(raw)
        assert s.session_id == "sess-abc"
        assert s.project_name == "my-proj"
        assert s.tool == "claude"
        assert s.display_status == "RUNNING"
        assert s.micro_state == "thinking"
        assert s.prompt_preview == "refactor the auth module"
        assert s.cost_usd == pytest.approx(0.0123)
        assert s.turn_count == 3
        assert s.model == "claude-sonnet-4-6"
        assert s.git_branch == "feat/auth"

    def test_token_fields(self) -> None:
        s = _parse_session(_make_raw_session())
        assert s.token_input == 1000
        assert s.token_output == 500
        assert s.token_cache_read == 200
        assert s.token_cache_write == 100

    def test_total_tokens(self) -> None:
        s = _parse_session(_make_raw_session())
        assert s.total_tokens == 1800  # 1000 + 500 + 200 + 100

    def test_missing_optional_fields_default_to_none(self) -> None:
        raw = _make_raw_session(activeToolName=None, gitBranch=None, userPromptPreview=None)
        s = _parse_session(raw)
        assert s.active_tool is None
        assert s.git_branch is None
        assert s.prompt_preview is None

    def test_missing_token_usage(self) -> None:
        raw = _make_raw_session()
        del raw["tokenUsage"]
        s = _parse_session(raw)
        assert s.token_input == 0
        assert s.total_tokens == 0

    def test_format_age_seconds(self) -> None:
        raw = _make_raw_session(startedAt=int(time.time() * 1000) - 30_000)
        s = _parse_session(raw)
        age = s.format_age()
        assert age.endswith("s")

    def test_format_age_minutes(self) -> None:
        raw = _make_raw_session(startedAt=int(time.time() * 1000) - 90_000)
        s = _parse_session(raw)
        assert s.format_age() == "1m"

    def test_format_age_hours(self) -> None:
        raw = _make_raw_session(startedAt=int(time.time() * 1000) - 4_500_000)
        s = _parse_session(raw)
        assert s.format_age().startswith("1h")


# ── fetch_state ────────────────────────────────────────────────────────────────

class TestFetchState:
    def test_returns_empty_on_import_error(self, monkeypatch) -> None:
        monkeypatch.setitem(__builtins__ if isinstance(__builtins__, dict) else {}, "httpx", None)
        with patch.dict("sys.modules", {"httpx": None}):
            sessions, online = fetch_state(port=4242)
        assert sessions == []
        assert online is False

    def test_returns_empty_false_on_connection_error(self) -> None:
        mock_httpx = MagicMock()
        mock_httpx.get.side_effect = Exception("connection refused")
        with patch.dict("sys.modules", {"httpx": mock_httpx}):
            sessions, online = fetch_state(port=4242)
        assert sessions == []
        assert online is False

    def test_parses_sessions_from_payload(self) -> None:
        now_ms = int(time.time() * 1000)
        raw = _make_raw_session(lastActiveAt=now_ms - 100)
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"sessions": [raw]}
        mock_httpx = MagicMock()
        mock_httpx.get.return_value = mock_resp
        with patch.dict("sys.modules", {"httpx": mock_httpx}):
            sessions, online = fetch_state(port=4242, hours=2.0)
        assert online is True
        assert len(sessions) == 1
        assert sessions[0].session_id == "sess-abc"

    def test_filters_old_sessions(self) -> None:
        now_ms = int(time.time() * 1000)
        old_raw = _make_raw_session(
            sessionId="old",
            lastActiveAt=now_ms - 10_000_000,  # ~2.7 hours ago
        )
        new_raw = _make_raw_session(
            sessionId="new",
            lastActiveAt=now_ms - 100,
        )
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"sessions": [old_raw, new_raw]}
        mock_httpx = MagicMock()
        mock_httpx.get.return_value = mock_resp
        with patch.dict("sys.modules", {"httpx": mock_httpx}):
            sessions, _ = fetch_state(port=4242, hours=2.0)
        assert len(sessions) == 1
        assert sessions[0].session_id == "new"

    def test_sorts_running_first(self) -> None:
        now_ms = int(time.time() * 1000)
        idle_raw = _make_raw_session(
            sessionId="idle-1", microState="idle", lastActiveAt=now_ms - 100
        )
        running_raw = _make_raw_session(
            sessionId="running-1", microState="thinking", lastActiveAt=now_ms - 100
        )
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"sessions": [idle_raw, running_raw]}
        mock_httpx = MagicMock()
        mock_httpx.get.return_value = mock_resp
        with patch.dict("sys.modules", {"httpx": mock_httpx}):
            sessions, _ = fetch_state(port=4242, hours=2.0)
        assert sessions[0].session_id == "running-1"
        assert sessions[1].session_id == "idle-1"

    def test_skips_malformed_entries(self) -> None:
        now_ms = int(time.time() * 1000)
        good_raw = _make_raw_session(lastActiveAt=now_ms - 100)
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"sessions": ["not_a_dict", good_raw, 42]}
        mock_httpx = MagicMock()
        mock_httpx.get.return_value = mock_resp
        with patch.dict("sys.modules", {"httpx": mock_httpx}):
            sessions, _ = fetch_state(port=4242, hours=2.0)
        assert len(sessions) == 1


# ── _parse_activity_event ──────────────────────────────────────────────────────

class TestParseActivityEvent:
    def test_basic_fields(self) -> None:
        raw = _make_raw_activity()
        ev = _parse_activity_event(raw)
        assert ev.event_id == "evt-uuid-001"
        assert ev.event_type == "phase_hint"
        assert ev.project_name == "my-proj"
        assert ev.epic_name == "auth-refactor"
        assert ev.epic_title == "Auth Refactor"
        assert ev.session_id == "sess-abc"
        assert ev.agent_name == "staff-engineer"
        assert ev.phase_id == "1"

    def test_optional_fields_absent(self) -> None:
        raw = _make_raw_activity()
        for key in ("epicName", "epicTitle", "sessionId", "agentName", "phaseId"):
            raw.pop(key, None)
        ev = _parse_activity_event(raw)
        assert ev.epic_name is None
        assert ev.session_id is None
        assert ev.agent_name is None

    def test_format_time_returns_nonempty(self) -> None:
        ev = _parse_activity_event(_make_raw_activity())
        t = ev.format_time()
        assert isinstance(t, str)
        assert ":" in t

    def test_format_age_seconds(self) -> None:
        raw = _make_raw_activity(timestamp=int(time.time() * 1000) - 5_000)
        ev = _parse_activity_event(raw)
        assert ev.format_age().endswith("s")


# ── fetch_activity ─────────────────────────────────────────────────────────────

class TestFetchActivity:
    def test_returns_empty_false_on_error(self) -> None:
        mock_httpx = MagicMock()
        mock_httpx.get.side_effect = Exception("refused")
        with patch.dict("sys.modules", {"httpx": mock_httpx}):
            events, online = fetch_activity(port=4242)
        assert events == []
        assert online is False

    def test_parses_events(self) -> None:
        raw = _make_raw_activity()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"events": [raw], "total": 1}
        mock_httpx = MagicMock()
        mock_httpx.get.return_value = mock_resp
        with patch.dict("sys.modules", {"httpx": mock_httpx}):
            events, online = fetch_activity(port=4242)
        assert online is True
        assert len(events) == 1
        assert events[0].event_type == "phase_hint"

    def test_skips_malformed_entries(self) -> None:
        raw = _make_raw_activity()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"events": ["bad", raw, None], "total": 3}
        mock_httpx = MagicMock()
        mock_httpx.get.return_value = mock_resp
        with patch.dict("sys.modules", {"httpx": mock_httpx}):
            events, _ = fetch_activity(port=4242)
        assert len(events) == 1


# ── fetch_single_session ───────────────────────────────────────────────────────

class TestFetchSingleSession:
    def _make_fetch_state_sessions(self):
        now_ms = int(time.time() * 1000)
        raw_a = _make_raw_session(sessionId="sess-aaa", lastActiveAt=now_ms - 100)
        raw_b = _make_raw_session(sessionId="sess-bbb", lastActiveAt=now_ms - 100)
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"sessions": [raw_a, raw_b]}
        mock_httpx = MagicMock()
        mock_httpx.get.return_value = mock_resp
        return mock_httpx

    def test_finds_session_by_id(self) -> None:
        mock_httpx = self._make_fetch_state_sessions()
        with patch.dict("sys.modules", {"httpx": mock_httpx}):
            session, online = fetch_single_session(port=4242, session_id="sess-bbb")
        assert online is True
        assert session is not None
        assert session.session_id == "sess-bbb"

    def test_returns_none_when_id_not_found(self) -> None:
        mock_httpx = self._make_fetch_state_sessions()
        with patch.dict("sys.modules", {"httpx": mock_httpx}):
            session, online = fetch_single_session(port=4242, session_id="no-such-id")
        assert online is True
        assert session is None

    def test_returns_none_when_no_session_id_given(self) -> None:
        mock_httpx = self._make_fetch_state_sessions()
        with patch.dict("sys.modules", {"httpx": mock_httpx}):
            session, online = fetch_single_session(port=4242, session_id="")
        assert session is None
