"""Tests for fetch_menu_stats and MenuStats in rover.api.

Covers:
  - Returns zeroed MenuStats with server_online=False when httpx raises
  - Correctly counts agent_count and running_count from a mixed session list
  - Aggregates tokens_by_provider keyed by the session's tool field
  - Excludes sessions whose lastActiveAt is outside the requested time window
  - Returns server_online=True when the server responds but sessions list is absent
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest

from rover.api import MenuStats, fetch_menu_stats


# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_raw_session(**overrides) -> dict:
    """Minimal raw session dict with sane defaults for fetch_menu_stats tests."""
    base = {
        "sessionId": "sess-default",
        "projectName": "proj",
        "tool": "claude",
        "microState": "idle",
        "activeToolName": None,
        "userPromptPreview": None,
        "startedAt": int(time.time() * 1000) - 60_000,
        "lastActiveAt": int(time.time() * 1000) - 5_000,
        "costUsd": 0.0,
        "turnCount": 0,
        "model": "claude-sonnet-4-6",
        "gitBranch": None,
        "tokenUsage": {
            "input": 0,
            "output": 0,
            "cacheRead": 0,
            "cacheWrite": 0,
        },
    }
    base.update(overrides)
    return base


def _mock_httpx_with_payload(payload: dict) -> MagicMock:
    """Return a mock httpx module whose .get() returns the given JSON payload."""
    mock_resp = MagicMock()
    mock_resp.json.return_value = payload
    mock_httpx = MagicMock()
    mock_httpx.get.return_value = mock_resp
    return mock_httpx


# ── TestFetchMenuStatsOnError ──────────────────────────────────────────────────

class TestFetchMenuStatsOnError:
    def test_returns_zero_stats_on_error(self) -> None:
        """When httpx raises, fetch_menu_stats returns all-zero MenuStats with online=False."""
        mock_httpx = MagicMock()
        mock_httpx.get.side_effect = Exception("connection refused")
        with patch.dict("sys.modules", {"httpx": mock_httpx}):
            stats = fetch_menu_stats(port=4242)
        assert isinstance(stats, MenuStats)
        assert stats.server_online is False
        assert stats.agent_count == 0
        assert stats.running_count == 0
        assert stats.total_tokens == 0
        assert stats.total_cost_usd == 0.0
        assert stats.tokens_by_provider == {}

    def test_returns_zero_stats_when_httpx_not_installed(self) -> None:
        """When httpx is absent, fetch_menu_stats returns zeroed stats rather than crashing."""
        with patch.dict("sys.modules", {"httpx": None}):
            stats = fetch_menu_stats(port=4242)
        assert stats.server_online is False
        assert stats.agent_count == 0

    def test_returns_online_true_when_sessions_key_absent(self) -> None:
        """Server is reachable but payload has no 'sessions' key — online=True, counts zero."""
        mock_httpx = _mock_httpx_with_payload({"status": "ok"})
        with patch.dict("sys.modules", {"httpx": mock_httpx}):
            stats = fetch_menu_stats(port=4242)
        assert stats.server_online is True
        assert stats.agent_count == 0


# ── TestFetchMenuStatsSessionCounting ─────────────────────────────────────────

class TestFetchMenuStatsSessionCounting:
    def test_parses_running_sessions(self) -> None:
        """Two sessions (one thinking, one idle) → agent_count=2, running_count=1."""
        now_ms = int(time.time() * 1000)
        thinking = _make_raw_session(
            sessionId="s1", microState="thinking", lastActiveAt=now_ms - 100
        )
        idle = _make_raw_session(
            sessionId="s2", microState="idle", lastActiveAt=now_ms - 200
        )
        mock_httpx = _mock_httpx_with_payload({"sessions": [thinking, idle]})
        with patch.dict("sys.modules", {"httpx": mock_httpx}):
            stats = fetch_menu_stats(port=4242, hours=1.0)
        assert stats.server_online is True
        assert stats.agent_count == 2
        assert stats.running_count == 1

    def test_all_running_states_increment_running_count(self) -> None:
        """thinking, tool_use, and researching all map to RUNNING."""
        now_ms = int(time.time() * 1000)
        sessions = [
            _make_raw_session(sessionId=f"s{i}", microState=state, lastActiveAt=now_ms - 100)
            for i, state in enumerate(["thinking", "tool_use", "researching"])
        ]
        mock_httpx = _mock_httpx_with_payload({"sessions": sessions})
        with patch.dict("sys.modules", {"httpx": mock_httpx}):
            stats = fetch_menu_stats(port=4242, hours=1.0)
        assert stats.agent_count == 3
        assert stats.running_count == 3

    def test_excludes_sessions_outside_time_window(self) -> None:
        """Sessions with lastActiveAt older than hours are not counted."""
        now_ms = int(time.time() * 1000)
        recent = _make_raw_session(sessionId="recent", lastActiveAt=now_ms - 100)
        old = _make_raw_session(
            sessionId="old",
            lastActiveAt=now_ms - int(2 * 3600 * 1000),  # 2 hours ago, outside 1h window
        )
        mock_httpx = _mock_httpx_with_payload({"sessions": [recent, old]})
        with patch.dict("sys.modules", {"httpx": mock_httpx}):
            stats = fetch_menu_stats(port=4242, hours=1.0)
        assert stats.agent_count == 1

    def test_empty_sessions_list_returns_zero_counts(self) -> None:
        """An empty sessions array is valid — server is online, all counts are zero."""
        mock_httpx = _mock_httpx_with_payload({"sessions": []})
        with patch.dict("sys.modules", {"httpx": mock_httpx}):
            stats = fetch_menu_stats(port=4242, hours=1.0)
        assert stats.server_online is True
        assert stats.agent_count == 0
        assert stats.running_count == 0


# ── TestFetchMenuStatsTokenAggregation ────────────────────────────────────────

class TestFetchMenuStatsTokenAggregation:
    def test_tokens_by_provider(self) -> None:
        """Session with tool='claude' and known token counts appears in tokens_by_provider."""
        now_ms = int(time.time() * 1000)
        session = _make_raw_session(
            sessionId="s1",
            tool="claude",
            lastActiveAt=now_ms - 100,
            tokenUsage={
                "input": 1000,
                "output": 500,
                "cacheRead": 200,
                "cacheWrite": 100,
            },
        )
        mock_httpx = _mock_httpx_with_payload({"sessions": [session]})
        with patch.dict("sys.modules", {"httpx": mock_httpx}):
            stats = fetch_menu_stats(port=4242, hours=1.0)
        assert "claude" in stats.tokens_by_provider
        assert stats.tokens_by_provider["claude"] == 1800  # 1000+500+200+100
        assert stats.total_tokens == 1800

    def test_tokens_aggregated_across_providers(self) -> None:
        """Two sessions with different tools each contribute to their provider bucket."""
        now_ms = int(time.time() * 1000)
        claude_session = _make_raw_session(
            sessionId="c1",
            tool="claude",
            lastActiveAt=now_ms - 100,
            tokenUsage={"input": 400, "output": 100, "cacheRead": 0, "cacheWrite": 0},
        )
        gemini_session = _make_raw_session(
            sessionId="g1",
            tool="gemini",
            lastActiveAt=now_ms - 100,
            tokenUsage={"input": 200, "output": 50, "cacheRead": 0, "cacheWrite": 0},
        )
        mock_httpx = _mock_httpx_with_payload({"sessions": [claude_session, gemini_session]})
        with patch.dict("sys.modules", {"httpx": mock_httpx}):
            stats = fetch_menu_stats(port=4242, hours=1.0)
        assert stats.tokens_by_provider["claude"] == 500
        assert stats.tokens_by_provider["gemini"] == 250
        assert stats.total_tokens == 750

    def test_tokens_accumulated_for_same_provider(self) -> None:
        """Two sessions with the same tool are summed into one provider bucket."""
        now_ms = int(time.time() * 1000)
        s1 = _make_raw_session(
            sessionId="c1",
            tool="claude",
            lastActiveAt=now_ms - 100,
            tokenUsage={"input": 300, "output": 0, "cacheRead": 0, "cacheWrite": 0},
        )
        s2 = _make_raw_session(
            sessionId="c2",
            tool="claude",
            lastActiveAt=now_ms - 200,
            tokenUsage={"input": 700, "output": 0, "cacheRead": 0, "cacheWrite": 0},
        )
        mock_httpx = _mock_httpx_with_payload({"sessions": [s1, s2]})
        with patch.dict("sys.modules", {"httpx": mock_httpx}):
            stats = fetch_menu_stats(port=4242, hours=1.0)
        assert stats.tokens_by_provider["claude"] == 1000

    def test_cost_summed_across_sessions(self) -> None:
        """total_cost_usd is the sum of costUsd across all in-window sessions."""
        now_ms = int(time.time() * 1000)
        s1 = _make_raw_session(sessionId="c1", lastActiveAt=now_ms - 100, costUsd=0.05)
        s2 = _make_raw_session(sessionId="c2", lastActiveAt=now_ms - 200, costUsd=0.03)
        mock_httpx = _mock_httpx_with_payload({"sessions": [s1, s2]})
        with patch.dict("sys.modules", {"httpx": mock_httpx}):
            stats = fetch_menu_stats(port=4242, hours=1.0)
        assert stats.total_cost_usd == pytest.approx(0.08)
