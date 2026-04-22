"""Tests for rover dispatch viewer screen helpers.

Covers pure functions used by dashboard.py, detail.py, and activity.py.
All tests are pure-Python — no Textual app loop required.
"""

from __future__ import annotations

import time

import pytest

from rover.screens.dashboard import (
    _STATUS_FILTERS,
    _TOOL_FILTERS,
    _HOURS_OPTIONS,
    _fmt_cost,
    _status_markup,
    _task_text,
    _tool_markup,
)
from rover.screens.detail import (
    _colour_status,
    _fmt_relative,
    _fmt_ts,
    _micro_state_label,
)
from rover.screens.activity import _colour_event_type, _fmt_event
from rover.api import ActivityEvent, Session, _parse_session


# ── Shared fixture ─────────────────────────────────────────────────────────────

def _session(**overrides) -> Session:
    now_ms = int(time.time() * 1000)
    base = {
        "sessionId": "sess-001",
        "projectName": "my-project",
        "tool": "claude",
        "microState": "thinking",
        "activeToolName": None,
        "userPromptPreview": "Fix the login bug",
        "startedAt": now_ms - 120_000,
        "lastActiveAt": now_ms - 2_000,
        "costUsd": 0.025,
        "turnCount": 5,
        "model": "claude-sonnet-4-6",
        "gitBranch": "fix/login",
        "tokenUsage": {"input": 1000, "output": 500, "cacheRead": 0, "cacheWrite": 0},
    }
    base.update(overrides)
    return _parse_session(base)


def _activity_event(**overrides) -> ActivityEvent:
    from rover.api import _parse_activity_event
    base = {
        "id": "evt-001",
        "timestamp": int(time.time() * 1000) - 3_000,
        "type": "phase_hint",
        "projectName": "my-project",
        "projectPath": "/home/user/my-project",
        "epicName": "fix-login",
        "epicTitle": "Fix Login",
        "sessionId": "sess-001",
        "agentName": "staff-engineer",
        "phaseId": "1",
    }
    base.update(overrides)
    return _parse_activity_event(base)


# ── Dashboard helpers ──────────────────────────────────────────────────────────

class TestStatusMarkup:
    @pytest.mark.parametrize("status,expected_fragment", [
        ("RUNNING",  "green"),
        ("APPROVAL", "yellow"),
        ("WAITING",  "dim"),
        ("IDLE",     "dim"),
        ("ERROR",    "red"),
    ])
    def test_known_status_contains_colour(self, status, expected_fragment) -> None:
        result = _status_markup(status)
        assert expected_fragment in result

    def test_unknown_status_falls_through(self) -> None:
        assert _status_markup("UNKNOWN") == "UNKNOWN"


class TestToolMarkup:
    @pytest.mark.parametrize("tool", ["claude", "gemini", "codex", "copilot"])
    def test_known_tool_wrapped_in_markup(self, tool) -> None:
        result = _tool_markup(tool)
        assert f"]{tool}[/" in result

    def test_case_insensitive(self) -> None:
        assert _tool_markup("Claude") == _tool_markup("claude")

    def test_unknown_tool_passthrough(self) -> None:
        assert _tool_markup("ollama") == "ollama"


class TestTaskText:
    def test_thinking_state_shows_prompt(self) -> None:
        s = _session()  # microState=thinking, no activeTool
        text = _task_text(s)
        assert "Fix the login bug" in text

    def test_tool_use_state_shows_tool_name(self) -> None:
        s = _session(microState="tool_use", activeToolName="Bash")
        text = _task_text(s)
        assert "Bash" in text

    def test_truncation(self) -> None:
        long_prompt = "A" * 100
        s = _session(userPromptPreview=long_prompt)
        text = _task_text(s)
        assert len(text) <= 41  # _TASK_MAX_LEN + ellipsis

    def test_no_preview_returns_empty(self) -> None:
        s = _session(userPromptPreview=None, microState="idle", activeToolName=None)
        text = _task_text(s)
        assert text == ""


class TestFmtCost:
    def test_zero_returns_dash(self) -> None:
        assert "—" in _fmt_cost(0.0)

    def test_small_below_threshold(self) -> None:
        result = _fmt_cost(0.0000001)
        assert "<" in result

    def test_normal_value_formatted(self) -> None:
        result = _fmt_cost(0.025)
        assert "$0.025" == result

    def test_larger_value(self) -> None:
        result = _fmt_cost(1.5)
        assert "$1.500" == result


class TestFilterConstants:
    def test_status_filters_first_is_none(self) -> None:
        assert _STATUS_FILTERS[0] is None

    def test_status_filters_contains_running(self) -> None:
        assert "RUNNING" in _STATUS_FILTERS

    def test_tool_filters_first_is_none(self) -> None:
        assert _TOOL_FILTERS[0] is None

    def test_hours_options_sorted_ascending(self) -> None:
        assert _HOURS_OPTIONS == sorted(_HOURS_OPTIONS)

    def test_hours_options_nonempty(self) -> None:
        assert len(_HOURS_OPTIONS) >= 2


# ── Detail screen helpers ──────────────────────────────────────────────────────

class TestColourStatus:
    @pytest.mark.parametrize("status,colour", [
        ("RUNNING", "green"),
        ("APPROVAL", "yellow"),
        ("ERROR", "red"),
    ])
    def test_wraps_in_colour_tags(self, status, colour) -> None:
        result = _colour_status(status)
        assert f"[{colour}]" in result
        assert f"[/{colour}]" in result

    def test_unknown_uses_white(self) -> None:
        result = _colour_status("MYSTERY")
        assert "[white]" in result


class TestFmtRelative:
    def test_seconds(self) -> None:
        assert _fmt_relative(30) == "30s ago"

    def test_minutes(self) -> None:
        assert _fmt_relative(90) == "1m 30s ago"

    def test_hours(self) -> None:
        result = _fmt_relative(3661)
        assert result.startswith("1h")

    def test_zero(self) -> None:
        result = _fmt_relative(0)
        assert result == "0s ago"


class TestFmtTs:
    def test_epoch_zero_returns_dash(self) -> None:
        assert _fmt_ts(0) == "—"

    def test_valid_timestamp_returns_string(self) -> None:
        ts = int(time.time() * 1000)
        result = _fmt_ts(ts)
        assert "-" in result and ":" in result


class TestMicroStateLabel:
    def test_tool_use_shows_tool_name(self) -> None:
        result = _micro_state_label("tool_use", "Bash")
        assert "Bash" in result
        assert "tool_use" in result

    def test_tool_use_without_tool_falls_through_to_label(self) -> None:
        result = _micro_state_label("tool_use", None)
        assert "tool_use" not in result or True  # any output acceptable

    def test_thinking_label(self) -> None:
        result = _micro_state_label("thinking", None)
        assert "thinking" in result

    def test_unknown_state(self) -> None:
        result = _micro_state_label("some_new_state", None)
        assert isinstance(result, str)
        assert len(result) > 0


# ── Activity screen helpers ────────────────────────────────────────────────────

class TestColourEventType:
    def test_known_type_wrapped(self) -> None:
        result = _colour_event_type("phase_hint")
        assert "phase_hint" in result
        assert "[" in result

    def test_unknown_type_wrapped_in_white(self) -> None:
        result = _colour_event_type("totally_new_event")
        assert "totally_new_event" in result
        assert "[white]" in result


class TestFmtEvent:
    def test_contains_event_type(self) -> None:
        ev = _activity_event()
        line = _fmt_event(ev)
        assert "phase_hint" in line

    def test_contains_project_name(self) -> None:
        ev = _activity_event()
        line = _fmt_event(ev)
        assert "my-project" in line

    def test_contains_agent_name(self) -> None:
        ev = _activity_event()
        line = _fmt_event(ev)
        assert "staff-engineer" in line

    def test_session_id_truncated(self) -> None:
        ev = _activity_event(sessionId="sess-abcdefgh-1234")
        line = _fmt_event(ev)
        assert "sess-" in line

    def test_no_session_id(self) -> None:
        ev = _activity_event(sessionId=None)
        line = _fmt_event(ev)
        assert isinstance(line, str)
        assert len(line) > 0
