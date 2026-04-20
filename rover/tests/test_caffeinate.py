"""Tests for the caffeinate manager.

Covers: availability detection, PID file lifecycle, idempotent
wake/sleep, toggle, stale-pid cleanup. We never actually spawn
`caffeinate` — the subprocess is mocked so tests run on any platform.
"""

from __future__ import annotations

import os
import pathlib
import sys

import pytest

from rover import caffeinate


@pytest.fixture(autouse=True)
def redirect_pid_file(tmp_path, monkeypatch):
    """Point the module's PID file at a tmp path so tests never touch real state."""
    monkeypatch.setattr(caffeinate, "_PID_FILE", tmp_path / "caffeinate.pid")
    yield


class TestAvailability:
    def test_available_on_darwin_with_caffeinate(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "darwin")
        monkeypatch.setattr(
            "rover.caffeinate.shutil.which",
            lambda name: "/usr/bin/caffeinate" if name == "caffeinate" else None,
        )
        assert caffeinate.is_available() is True

    def test_unavailable_on_linux(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "linux")
        assert caffeinate.is_available() is False

    def test_unavailable_on_darwin_without_binary(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "darwin")
        monkeypatch.setattr("rover.caffeinate.shutil.which", lambda name: None)
        assert caffeinate.is_available() is False


class TestPidLifecycle:
    def test_is_awake_false_when_no_pid_file(self):
        assert caffeinate.is_awake() is False

    def test_is_awake_true_when_pid_alive(self, monkeypatch):
        # The current test process is obviously alive
        caffeinate._PID_FILE.write_text(str(os.getpid()))
        assert caffeinate.is_awake() is True

    def test_is_awake_clears_stale_pid_file(self, monkeypatch):
        # Use a PID that's almost certainly not running
        caffeinate._PID_FILE.write_text("99999999")
        assert caffeinate.is_awake() is False
        # Stale file should have been removed
        assert not caffeinate._PID_FILE.exists()

    def test_is_awake_with_malformed_pid(self):
        caffeinate._PID_FILE.write_text("not-a-number")
        assert caffeinate.is_awake() is False


class TestWakeSleep:
    def test_wake_writes_pid_file(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "darwin")
        monkeypatch.setattr(
            "rover.caffeinate.shutil.which", lambda n: "/usr/bin/caffeinate"
        )

        fake_pid = 12345

        class _FakeProc:
            pid = fake_pid

        monkeypatch.setattr(
            "rover.caffeinate.subprocess.Popen",
            lambda *args, **kwargs: _FakeProc(),
        )
        # _pid_alive for our fake pid → say it's alive
        monkeypatch.setattr("rover.caffeinate._pid_alive", lambda p: True)

        assert caffeinate.wake() is True
        assert caffeinate._PID_FILE.read_text() == str(fake_pid)

    def test_wake_idempotent_when_already_awake(self, monkeypatch):
        caffeinate._PID_FILE.write_text(str(os.getpid()))

        spawned = []
        monkeypatch.setattr(
            "rover.caffeinate.subprocess.Popen",
            lambda *a, **kw: spawned.append(1) or None,
        )
        assert caffeinate.wake() is True
        assert spawned == [], "Popen must not be called when already awake"

    def test_wake_unavailable_platform(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "linux")
        assert caffeinate.wake() is False
        assert not caffeinate._PID_FILE.exists()

    def test_sleep_kills_tracked_pid(self, monkeypatch):
        caffeinate._PID_FILE.write_text("12345")

        killed = []
        def fake_kill(pid, sig):
            killed.append((pid, sig))
        monkeypatch.setattr("rover.caffeinate.os.kill", fake_kill)

        assert caffeinate.sleep() is True
        assert killed == [(12345, 15)]  # SIGTERM = 15
        assert not caffeinate._PID_FILE.exists()

    def test_sleep_idempotent_when_no_pid(self):
        assert caffeinate.sleep() is True

    def test_sleep_cleans_up_when_process_already_gone(self, monkeypatch):
        caffeinate._PID_FILE.write_text("12345")
        def raise_lookup(pid, sig):
            raise ProcessLookupError
        monkeypatch.setattr("rover.caffeinate.os.kill", raise_lookup)

        assert caffeinate.sleep() is True
        assert not caffeinate._PID_FILE.exists()


class TestToggle:
    def test_toggle_awake_to_sleep(self, monkeypatch):
        caffeinate._PID_FILE.write_text(str(os.getpid()))
        monkeypatch.setattr("rover.caffeinate.os.kill", lambda pid, sig: None)
        assert caffeinate.toggle() is False
        assert not caffeinate._PID_FILE.exists()

    def test_toggle_sleep_to_awake(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "darwin")
        monkeypatch.setattr(
            "rover.caffeinate.shutil.which", lambda n: "/usr/bin/caffeinate"
        )

        class _FakeProc:
            pid = 54321

        monkeypatch.setattr(
            "rover.caffeinate.subprocess.Popen",
            lambda *a, **kw: _FakeProc(),
        )
        monkeypatch.setattr("rover.caffeinate._pid_alive", lambda p: True)

        assert caffeinate.toggle() is True
        assert caffeinate._PID_FILE.read_text() == "54321"
