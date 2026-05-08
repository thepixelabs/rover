"""Minimal append-only local telemetry for rover.

Writes one JSON line per event to ~/.rover/events.jsonl.  Every call is
wrapped in try/except so telemetry can never crash the caller.

Rotation: when the file exceeds _MAX_BYTES the oldest _DROP_LINES lines are
dropped in-place.  This keeps the file bounded without losing the most recent
events.
"""

from __future__ import annotations

import json
import pathlib
import time
from typing import Any

_ROVER_DIR = pathlib.Path.home() / ".rover"
_EVENTS_FILE = _ROVER_DIR / "events.jsonl"
_MAX_BYTES = 100 * 1024   # 100 KB
_DROP_LINES = 200         # lines to discard when rotating


def _emit(event: dict[str, Any]) -> None:
    """Append *event* (enriched with a UTC timestamp) to ~/.rover/events.jsonl.

    Never raises — all exceptions are silently swallowed so a telemetry
    failure cannot disrupt rover's main control flow.
    """
    try:
        _ROVER_DIR.mkdir(parents=True, exist_ok=True)

        record = {"ts": time.time(), **event}
        line = json.dumps(record, ensure_ascii=False) + "\n"

        # Rotate before writing so we don't push the file over the limit and
        # then immediately truncate the entry we just wrote.
        _maybe_rotate()

        with _EVENTS_FILE.open("a", encoding="utf-8") as fh:
            fh.write(line)
    except Exception:
        pass


def _maybe_rotate() -> None:
    """If events.jsonl exceeds _MAX_BYTES, drop the oldest _DROP_LINES lines."""
    try:
        if not _EVENTS_FILE.exists():
            return
        if _EVENTS_FILE.stat().st_size <= _MAX_BYTES:
            return

        with _EVENTS_FILE.open("r", encoding="utf-8", errors="replace") as fh:
            lines = fh.readlines()

        if len(lines) <= _DROP_LINES:
            # File is small in line count but large — wipe it entirely.
            _EVENTS_FILE.write_text("", encoding="utf-8")
            return

        kept = lines[_DROP_LINES:]
        with _EVENTS_FILE.open("w", encoding="utf-8") as fh:
            fh.writelines(kept)
    except Exception:
        pass
