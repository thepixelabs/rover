"""ActivityScreen — live activity event log for rover.

Connects to GET /api/activity and polls every 2 s to show a rolling feed of
server-side activity events.  When session_id is provided, events are filtered
to that session.

Key bindings:
  q / Esc   — return to previous screen
  r         — force immediate refresh
  c         — clear the displayed log (does not affect server)
"""

from __future__ import annotations

import threading
import time
from typing import Optional

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Label, RichLog, Static

from rover.api import ActivityEvent, fetch_activity
from rover.menu import _now_str

# ── Event-type colour map ──────────────────────────────────────────────────────

_TYPE_COLOURS: dict[str, str] = {
    "phase_hint":              "#00d7ff",
    "phase_started":           "green",
    "phase_completed":         "bright_green",
    "phase_blocked":           "yellow",
    "epic_started":            "cyan",
    "epic_completed":          "bright_cyan",
    "agent_synced":            "dim white",
    "agent_conflict_detected": "red",
    "agent.spawn":             "magenta",
    "agent.install.succeeded": "green",
    "agent.install.failed":    "red",
}
_DEFAULT_COLOUR = "white"

_POLL_INTERVAL_S = 2.0
_MAX_LOG_LINES   = 300


def _colour_event_type(event_type: str) -> str:
    colour = _TYPE_COLOURS.get(event_type, _DEFAULT_COLOUR)
    return f"[{colour}]{event_type}[/{colour}]"


def _fmt_event(ev: ActivityEvent) -> str:
    """Format a single activity event into a one-line rich markup string."""
    ts = ev.format_time()
    etype = _colour_event_type(ev.event_type)
    project = f"[dim]{ev.project_name}[/dim]" if ev.project_name else ""
    epic = f"[dim] · {ev.epic_title or ev.epic_name}[/dim]" if (ev.epic_title or ev.epic_name) else ""
    agent = f"[dim] @{ev.agent_name}[/dim]" if ev.agent_name else ""
    session = f"[dim] sid={ev.session_id[:8]}[/dim]" if ev.session_id else ""
    return f"[dim]{ts}[/dim]  {etype}  {project}{epic}{agent}{session}"


# ── Screen ─────────────────────────────────────────────────────────────────────

class ActivityScreen(Screen):
    """Live activity event feed from the dispatch server."""

    DEFAULT_CSS = """
    ActivityScreen {
        background: #0d0d1a;
        align: center top;
        overflow-y: auto;
        overflow-x: hidden;
    }

    #act-outer {
        width: 100%;
        height: 1fr;
        border: solid #404060;
        padding: 0 1;
        margin: 0;
    }

    #act-header-row {
        height: 1;
        layout: horizontal;
    }

    #act-title {
        width: 1fr;
        color: #00d7ff;
        text-style: bold;
    }

    #act-clock {
        width: auto;
        color: #505070;
    }

    #act-divider {
        color: #404060;
        height: 1;
    }

    #act-filter-bar {
        height: 1;
        color: #505070;
    }

    #act-log {
        height: 1fr;
        background: #0a0a14;
        border: solid #1a1a3a;
        padding: 0 1;
        scrollbar-size-vertical: 1;
        scrollbar-background: #0a0a14;
        scrollbar-color: #1a1a2a;
        scrollbar-color-active: #00d7ff;
    }

    #act-status-bar {
        height: 1;
        dock: bottom;
        background: #1a1a3a;
        color: #808080;
    }
    """

    BINDINGS = [
        Binding("escape", "back", "Back"),
        Binding("q", "back", "Back"),
        Binding("r", "refresh_now", "Refresh"),
        Binding("c", "clear_log", "Clear"),
    ]

    def __init__(
        self,
        port: int = 4242,
        session_id: Optional[str] = None,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.port = port
        self.session_id = session_id
        self._last_event_ts: int = 0
        self._total_server: int = 0
        self._shown: int = 0
        self._server_online: bool = False

    # ── Composition ────────────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        with Vertical(id="act-outer"):
            with Horizontal(id="act-header-row"):
                yield Label("ACTIVITY LOG", id="act-title")
                yield Label(_now_str(), id="act-clock")
            yield Static("─" * 60, id="act-divider")
            yield Static("", id="act-filter-bar")
            yield RichLog(id="act-log", highlight=False, markup=True, max_lines=_MAX_LOG_LINES)
        yield Static("", id="act-status-bar")

    def on_mount(self) -> None:
        self._repaint_filter_bar()
        self._fetch_events(initial=True)
        self.set_interval(1.0, self._tick_clock)
        self.set_interval(_POLL_INTERVAL_S, self._poll_events)

    # ── Clock ──────────────────────────────────────────────────────────────────

    def _tick_clock(self) -> None:
        self.query_one("#act-clock", Label).update(_now_str())

    # ── Data fetch ─────────────────────────────────────────────────────────────

    def _fetch_events(self, initial: bool = False) -> None:
        since = 0 if initial else self._last_event_ts
        session_filter = self.session_id

        def _fetch() -> None:
            events, online = fetch_activity(
                port=self.port,
                since=since,
                limit=200 if initial else 100,
            )
            self.call_from_thread(self._apply_events, events, online, initial)

        threading.Thread(target=_fetch, daemon=True).start()

    def _poll_events(self) -> None:
        self._fetch_events(initial=False)

    def _apply_events(
        self,
        events: list[ActivityEvent],
        online: bool,
        initial: bool,
    ) -> None:
        self._server_online = online
        log = self.query_one("#act-log", RichLog)

        if initial:
            log.clear()
            self._shown = 0

        if not events:
            self._repaint_status_bar()
            return

        session_filter = self.session_id
        for ev in events:
            if session_filter and ev.session_id != session_filter:
                continue
            log.write(_fmt_event(ev))
            self._shown += 1
            if ev.timestamp_ms > self._last_event_ts:
                self._last_event_ts = ev.timestamp_ms

        self._repaint_status_bar()

    # ── Repainting ─────────────────────────────────────────────────────────────

    def _repaint_filter_bar(self) -> None:
        bar = self.query_one("#act-filter-bar", Static)
        if self.session_id:
            bar.update(
                f"  [dim]filter:[/dim] session [cyan]{self.session_id[:16]}…[/cyan]"
                f"  [bold #00d7ff]C[/bold #00d7ff] clear  "
                f"[bold #00d7ff]R[/bold #00d7ff] refresh  "
                f"[bold #00d7ff]q[/bold #00d7ff] back"
            )
        else:
            bar.update(
                f"  [dim]showing:[/dim] [cyan]all events[/cyan]"
                f"  [bold #00d7ff]C[/bold #00d7ff] clear  "
                f"[bold #00d7ff]R[/bold #00d7ff] refresh  "
                f"[bold #00d7ff]q[/bold #00d7ff] back"
            )

    def _repaint_status_bar(self) -> None:
        bar = self.query_one("#act-status-bar", Static)
        if self._server_online:
            bar.update(
                f"[dim]dispatch @ localhost:{self.port}"
                f"  |  {self._shown} events shown"
                f"  |  live (poll {_POLL_INTERVAL_S:.0f}s)[/dim]"
            )
        else:
            bar.update(f"[red]dispatch OFFLINE (port {self.port})[/red]")

    # ── Keyboard actions ───────────────────────────────────────────────────────

    def action_back(self) -> None:
        self.app.pop_screen()

    def action_refresh_now(self) -> None:
        self._fetch_events(initial=True)

    def action_clear_log(self) -> None:
        self.query_one("#act-log", RichLog).clear()
        self._shown = 0
        self._last_event_ts = 0
        self._repaint_status_bar()
