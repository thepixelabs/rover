"""Tests for rover.session_manager.

Covers:
  - TmuxSession.age_str() boundary values: 0s, 59s, 60s (=1m), 3599s (=59m),
    3600s (=1h), 3661s (=1h1m), 86399s (=23h59m), 86400s (=1d)
  - list_sessions() parser: parses tab-separated tmux output into TmuxSession objects,
    handles malformed lines, handles non-zero return code
"""

from __future__ import annotations

import subprocess
import time
from unittest.mock import MagicMock, patch


from rover.session_manager import TmuxSession, list_sessions


# ---------------------------------------------------------------------------
# TmuxSession.age_str() boundary values
# ---------------------------------------------------------------------------

class TestAgeStr:
    """age_str uses int(time.time()) - created_epoch, so we control the gap
    by passing created_epoch = int(time.time()) - desired_seconds."""

    def _session(self, seconds_ago: int) -> TmuxSession:
        return TmuxSession(
            name="test",
            attached=False,
            created_epoch=int(time.time()) - seconds_ago,
            window_count=1,
        )

    def test_zero_seconds(self):
        assert self._session(0).age_str() == "0s"

    def test_59_seconds(self):
        assert self._session(59).age_str() == "59s"

    def test_60_seconds_is_one_minute(self):
        assert self._session(60).age_str() == "1m"

    def test_59_minutes(self):
        assert self._session(59 * 60).age_str() == "59m"

    def test_exactly_one_hour_no_leftover(self):
        assert self._session(3600).age_str() == "1h"

    def test_one_hour_one_minute(self):
        assert self._session(3661).age_str() == "1h1m"

    def test_just_under_24_hours_with_leftover(self):
        # 23 * 3600 + 59*60 = 82800 + 3540 = 86340 seconds
        result = self._session(86340).age_str()
        assert result == "23h59m"

    def test_exactly_24_hours_returns_days(self):
        assert self._session(86400).age_str() == "1d"

    def test_48_hours_returns_two_days(self):
        assert self._session(2 * 86400).age_str() == "2d"


# ---------------------------------------------------------------------------
# list_sessions() parser
# ---------------------------------------------------------------------------

def _mock_run(stdout: str, returncode: int = 0):
    """Build a MagicMock that looks like a subprocess.CompletedProcess."""
    m = MagicMock()
    m.returncode = returncode
    m.stdout = stdout
    return m


class TestListSessionsParser:
    def test_parses_single_attached_session(self):
        raw = "my-session\t1\t1700000000\t2\n"
        with patch("rover.session_manager.subprocess.run", return_value=_mock_run(raw)):
            sessions = list_sessions()
        assert len(sessions) == 1
        s = sessions[0]
        assert s.name == "my-session"
        assert s.attached is True
        assert s.created_epoch == 1700000000
        assert s.window_count == 2

    def test_parses_multiple_sessions_and_sorts(self):
        # Two sessions: the older one is attached, newer is idle.
        raw = (
            "old-session\t1\t1699000000\t1\n"
            "new-session\t0\t1700000000\t3\n"
        )
        with patch("rover.session_manager.subprocess.run", return_value=_mock_run(raw)):
            sessions = list_sessions()
        assert len(sessions) == 2
        # Attached first
        assert sessions[0].attached is True
        assert sessions[0].name == "old-session"

    def test_returns_empty_list_on_nonzero_exit(self):
        with patch(
            "rover.session_manager.subprocess.run",
            return_value=_mock_run("", returncode=1),
        ):
            assert list_sessions() == []

    def test_skips_malformed_lines(self):
        raw = "bad-line-only-three-parts\t0\t12345\n"
        with patch("rover.session_manager.subprocess.run", return_value=_mock_run(raw)):
            assert list_sessions() == []

    def test_returns_empty_list_when_tmux_not_found(self):
        with patch(
            "rover.session_manager.subprocess.run",
            side_effect=FileNotFoundError,
        ):
            assert list_sessions() == []

    def test_returns_empty_list_on_timeout(self):
        with patch(
            "rover.session_manager.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="tmux", timeout=3),
        ):
            assert list_sessions() == []
