"""Tests for rover.telemetry.

Covers:
  - _emit writes a JSONL record with a 'ts' field
  - _emit never raises, even on completely bad input
  - _emit creates the directory if it does not exist
  - _maybe_rotate does nothing when file is small
  - _maybe_rotate drops oldest _DROP_LINES lines when file exceeds _MAX_BYTES
  - _maybe_rotate wipes file when line count <= _DROP_LINES but size > limit
  - Concurrent-ish writes (sequential in single thread) don't corrupt JSON
  - Each event record is independently parseable as JSON
"""

from __future__ import annotations

import json
import pathlib

import pytest

from rover.telemetry import _emit, _maybe_rotate, _DROP_LINES, _MAX_BYTES


# ---------------------------------------------------------------------------
# _emit — basic write
# ---------------------------------------------------------------------------

class TestEmitWrites:
    def test_emit_creates_jsonl_record(self, tmp_events_file):
        _emit({"event": "test_event"})
        lines = tmp_events_file.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 1
        record = json.loads(lines[0])
        assert record["event"] == "test_event"

    def test_emit_adds_ts_field(self, tmp_events_file):
        _emit({"event": "launch"})
        record = json.loads(tmp_events_file.read_text(encoding="utf-8").strip())
        assert "ts" in record
        assert isinstance(record["ts"], float)

    def test_emit_appends_multiple_records(self, tmp_events_file):
        _emit({"event": "first"})
        _emit({"event": "second"})
        _emit({"event": "third"})
        lines = tmp_events_file.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 3
        events = [json.loads(l)["event"] for l in lines]
        assert events == ["first", "second", "third"]

    def test_emit_creates_directory_if_missing(self, tmp_path, monkeypatch):
        """_emit must mkdir parents if the rover dir does not exist yet."""
        rover_dir = tmp_path / "new_rover_dir"
        events_file = rover_dir / "events.jsonl"
        import rover.telemetry as tel
        monkeypatch.setattr(tel, "_ROVER_DIR", rover_dir)
        monkeypatch.setattr(tel, "_EVENTS_FILE", events_file)
        # Directory does not exist yet
        assert not rover_dir.exists()
        _emit({"event": "dir_creation_test"})
        assert events_file.exists()


# ---------------------------------------------------------------------------
# _emit — never raises
# ---------------------------------------------------------------------------

class TestEmitNeverRaises:
    def test_emit_does_not_raise_on_non_serialisable_value(self, tmp_events_file):
        """A value that json.dumps cannot handle must not propagate an exception."""
        # Pass an object that json.dumps will fail on — _emit swallows it
        _emit({"bad": object()})  # type: ignore[arg-type]

    def test_emit_does_not_raise_when_directory_not_writable(self, tmp_path, monkeypatch):
        """If _ROVER_DIR is set to a path we cannot write to, _emit must stay silent."""
        import rover.telemetry as tel
        # Point at a file (not a directory) — mkdir will fail
        blocker = tmp_path / "blocker"
        blocker.write_text("not a dir")
        monkeypatch.setattr(tel, "_ROVER_DIR", blocker / "subdir")
        monkeypatch.setattr(tel, "_EVENTS_FILE", blocker / "subdir" / "events.jsonl")
        _emit({"event": "should_not_raise"})


# ---------------------------------------------------------------------------
# _maybe_rotate
# ---------------------------------------------------------------------------

class TestMaybeRotate:
    def test_no_rotation_when_file_is_small(self, tmp_events_file):
        """Small file (well under 100 KB) must not be modified."""
        content = '{"event": "x"}\n' * 10
        tmp_events_file.write_text(content, encoding="utf-8")
        _maybe_rotate()
        assert tmp_events_file.read_text(encoding="utf-8") == content

    def test_rotation_drops_oldest_lines_when_large(self, tmp_events_file):
        """When file > _MAX_BYTES and line count > _DROP_LINES, oldest lines are dropped."""
        # Create a file that exceeds _MAX_BYTES
        single_line = '{"event": "x", "padding": "' + "y" * 500 + '"}\n'
        total_lines = _DROP_LINES + 50  # safely above the drop threshold
        tmp_events_file.write_text(single_line * total_lines, encoding="utf-8")

        assert tmp_events_file.stat().st_size > _MAX_BYTES

        _maybe_rotate()

        remaining = tmp_events_file.read_text(encoding="utf-8").splitlines()
        assert len(remaining) == 50  # only the kept tail

    def test_rotation_wipes_file_when_line_count_small_but_size_large(self, tmp_events_file):
        """When file > _MAX_BYTES but has <= _DROP_LINES lines, wipe entirely."""
        # A single very large line that pushes size over the limit
        huge_line = '{"event": "big", "data": "' + "z" * (_MAX_BYTES + 1000) + '"}\n'
        tmp_events_file.write_text(huge_line, encoding="utf-8")

        _maybe_rotate()

        assert tmp_events_file.read_text(encoding="utf-8") == ""

    def test_rotation_does_nothing_when_file_absent(self, tmp_events_file):
        """When events.jsonl doesn't exist, _maybe_rotate returns silently."""
        # Don't create the file
        assert not tmp_events_file.exists()
        _maybe_rotate()  # must not raise


# ---------------------------------------------------------------------------
# Sequential writes stay valid JSON
# ---------------------------------------------------------------------------

class TestJsonIntegrity:
    def test_each_line_is_valid_json_after_many_emits(self, tmp_events_file):
        for i in range(20):
            _emit({"event": "iteration", "i": i})
        lines = tmp_events_file.read_text(encoding="utf-8").splitlines()
        for line in lines:
            record = json.loads(line)  # must not raise
            assert "ts" in record
