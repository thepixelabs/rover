"""DashboardScreen — the main dispatch viewer for rover.

Matches the visual language of MainMenuScreen: dark #0d0d1a theme, figlet
header, live clock, cyan accent keys, and a rich stats line.  Adds:

  • Filter bar  (f = cycle status filter, t = cycle tool filter)
  • Hours window (h = cycle 1 h / 2 h / 6 h / 24 h)
  • Digit quick-select (1-9) with accumulated number buffer
  • Live 1-second clock tick
  • Per-session token + cost columns
  • Auto-refresh every 5 s (driven by DispatchTuiApp.set_interval)
"""

from __future__ import annotations

import os
import threading
import time
from typing import Optional

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import DataTable, Label, Static

from rover.api import MenuStats, Session, fetch_menu_stats, fetch_state
from rover.menu import _figlet_renderable, _fmt_tokens, _now_str

# ── Constants ──────────────────────────────────────────────────────────────────

_TASK_MAX_LEN = 40

_STATUS_MARKUP: dict[str, str] = {
    "RUNNING":  "[green]RUNNING [/]",
    "APPROVAL": "[yellow]APPROVAL[/]",
    "WAITING":  "[dim]WAITING [/]",
    "IDLE":     "[dim]IDLE    [/]",
    "ERROR":    "[red]ERROR   [/]",
}

_TOOL_MARKUP: dict[str, str] = {
    "claude":  "[cyan]claude[/]",
    "gemini":  "[blue]gemini[/]",
    "codex":   "[magenta]codex[/]",
    "copilot": "[yellow]copilot[/]",
}

# Ordered status filter cycle: None = show all
_STATUS_FILTERS: list[Optional[str]] = [
    None, "RUNNING", "APPROVAL", "WAITING", "IDLE", "ERROR"
]

_TOOL_FILTERS: list[Optional[str]] = [
    None, "claude", "gemini", "codex", "copilot"
]

_HOURS_OPTIONS: list[float] = [1.0, 2.0, 6.0, 24.0]


# ── Helpers ────────────────────────────────────────────────────────────────────

def _status_markup(status: str) -> str:
    return _STATUS_MARKUP.get(status, status)


def _tool_markup(tool: str) -> str:
    return _TOOL_MARKUP.get(tool.lower(), tool)


def _task_text(session: Session) -> str:
    if session.micro_state == "tool_use" and session.active_tool:
        raw = f"[{session.active_tool}]"
    else:
        raw = (session.prompt_preview or "").replace("\n", " ").strip()
    if len(raw) > _TASK_MAX_LEN:
        return raw[:_TASK_MAX_LEN - 1] + "…"
    return raw


def _fmt_cost(cost_usd: float) -> str:
    if cost_usd == 0.0:
        return "[dim]—[/]"
    if cost_usd < 0.001:
        return f"[dim]<$0.001[/]"
    return f"${cost_usd:.3f}"


# ── Screen ─────────────────────────────────────────────────────────────────────

class DashboardScreen(Screen):
    """Main dispatch dashboard: agent sessions with live monitoring."""

    DEFAULT_CSS = """
    DashboardScreen {
        background: #0d0d1a;
        align: center top;
        overflow-y: auto;
        overflow-x: hidden;
        scrollbar-size-vertical: 1;
        scrollbar-background: #0d0d1a;
        scrollbar-color: #1a1a2a;
        scrollbar-color-hover: #2a3a4a;
        scrollbar-color-active: #00d7ff;
    }

    #dash-figlet {
        width: 100%;
        content-align: center middle;
        text-align: center;
        padding: 0;
        color: #5fff87;
    }

    #dash-box {
        width: 100%;
        height: auto;
        border: solid #404060;
        padding: 0 1;
        margin: 0;
    }

    #dash-header {
        height: 1;
        layout: horizontal;
    }

    #dash-title {
        width: 1fr;
        color: #00d7ff;
        text-style: bold;
    }

    #dash-clock {
        width: auto;
        content-align: right middle;
        color: #505070;
    }

    #dash-stats {
        height: auto;
        color: #606080;
        padding-bottom: 0;
    }

    #dash-div-top {
        color: #404060;
        height: 1;
    }

    #dash-filter {
        height: 1;
        color: #404060;
    }

    #agents-table {
        height: auto;
        border: none;
        padding: 0;
        margin: 0;
        background: #0d0d1a;
        scrollbar-size: 0 0;
    }

    #agents-table > .datatable--header {
        background: #1a1a3a;
        color: #00d7ff;
    }

    #agents-table > .datatable--cursor {
        background: #1a2a3a;
        color: #ffffff;
    }

    #dash-div-bot {
        color: #404060;
        height: 1;
        margin-top: 0;
    }

    #dash-actions {
        height: auto;
        padding: 0;
        margin: 0;
    }

    #dash-numbuf {
        color: #00d7ff;
        height: 1;
        padding-top: 0;
        text-align: center;
    }

    #dash-status-bar {
        height: 1;
        dock: bottom;
        background: #1a1a3a;
        color: #808080;
    }
    """

    BINDINGS = [
        Binding("j", "cursor_down", "Down", show=False),
        Binding("k", "cursor_up", "Up", show=False),
        Binding("down", "cursor_down", "Down", show=False),
        Binding("up", "cursor_up", "Up", show=False),
        Binding("enter", "select_session", "Detail"),
        Binding("r", "refresh_now", "Refresh"),
        Binding("f", "cycle_status_filter", "Filter status"),
        Binding("t", "cycle_tool_filter", "Filter tool"),
        Binding("h", "cycle_hours", "Hours window"),
        Binding("a", "open_activity", "Activity log"),
        Binding("1", "jump_row(1)", show=False),
        Binding("2", "jump_row(2)", show=False),
        Binding("3", "jump_row(3)", show=False),
        Binding("4", "jump_row(4)", show=False),
        Binding("5", "jump_row(5)", show=False),
        Binding("6", "jump_row(6)", show=False),
        Binding("7", "jump_row(7)", show=False),
        Binding("8", "jump_row(8)", show=False),
        Binding("9", "jump_row(9)", show=False),
    ]

    def __init__(self, port: int = 4242, hours: float = 2.0) -> None:
        super().__init__()
        self.port = port
        self.hours = hours

        self._sessions: list[Session] = []
        self._stats: Optional[MenuStats] = None
        self._server_online: bool = False
        self._last_update: Optional[float] = None

        self._status_filter_idx: int = 0
        self._tool_filter_idx: int = 0
        self._hours_idx: int = _HOURS_OPTIONS.index(hours) if hours in _HOURS_OPTIONS else 1

    # ── Composition ────────────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        try:
            term_w = os.get_terminal_size().columns
        except OSError:
            term_w = 80
        yield Static(_figlet_renderable("slant", "dispatch", term_w), id="dash-figlet")
        with Vertical(id="dash-box"):
            with Horizontal(id="dash-header"):
                yield Label("DISPATCH MONITOR", id="dash-title")
                yield Label(_now_str(), id="dash-clock")
            yield Static("", id="dash-stats")
            yield Static("─" * 60, id="dash-div-top")
            yield Static("", id="dash-filter")
            yield DataTable(id="agents-table", show_cursor=True)
            yield Static("─" * 60, id="dash-div-bot")
            yield Static("", id="dash-actions")
            yield Static("", id="dash-numbuf")
        yield Static("", id="dash-status-bar")

    def on_mount(self) -> None:
        table = self.query_one("#agents-table", DataTable)
        table.add_columns("#", "STATUS", "TOOL", "PROJECT", "TASK / TOOL", "AGE", "COST", "TOK")
        self.refresh_data()
        table.focus()
        self.set_interval(1.0, self._tick_clock)
        self._repaint_actions()

    # ── Clock tick ─────────────────────────────────────────────────────────────

    def _tick_clock(self) -> None:
        self.query_one("#dash-clock", Label).update(_now_str())

    # ── Data refresh ───────────────────────────────────────────────────────────

    def refresh_data(self) -> None:
        """Fetch data from dispatch in a background thread, then repaint."""
        def _fetch() -> None:
            sessions, online = fetch_state(port=self.port, hours=self.hours)
            stats = fetch_menu_stats(port=self.port, hours=self.hours)
            self.call_from_thread(self._apply_data, sessions, online, stats)

        t = threading.Thread(target=_fetch, daemon=True)
        t.start()

    def _apply_data(
        self,
        sessions: list[Session],
        online: bool,
        stats: MenuStats,
    ) -> None:
        self._sessions = sessions
        self._server_online = online
        self._stats = stats
        self._last_update = time.time()
        self._repaint_table()
        self._repaint_stats()
        self._repaint_filter_bar()
        self._repaint_status_bar()

    # ── Repainting helpers ─────────────────────────────────────────────────────

    def _visible_sessions(self) -> list[Session]:
        """Apply current status + tool filters."""
        status_filter = _STATUS_FILTERS[self._status_filter_idx]
        tool_filter = _TOOL_FILTERS[self._tool_filter_idx]
        result = self._sessions
        if status_filter is not None:
            result = [s for s in result if s.display_status == status_filter]
        if tool_filter is not None:
            result = [s for s in result if s.tool.lower() == tool_filter]
        return result

    def _repaint_table(self) -> None:
        table = self.query_one("#agents-table", DataTable)
        table.clear()
        visible = self._visible_sessions()
        for idx, session in enumerate(visible, start=1):
            tok_str = _fmt_tokens(session.total_tokens) if session.total_tokens else "[dim]—[/]"
            table.add_row(
                str(idx),
                _status_markup(session.display_status),
                _tool_markup(session.tool),
                session.project_name or "[dim]—[/]",
                _task_text(session),
                session.format_age(),
                _fmt_cost(session.cost_usd),
                tok_str,
            )

    def _repaint_stats(self) -> None:
        stats = self._stats
        stat_widget = self.query_one("#dash-stats", Static)
        if stats is None or not stats.server_online:
            stat_widget.update("[red]dispatch offline[/red]")
            return

        parts = [
            f"[green]● online[/green]",
            f"[dim]{stats.agent_count} agents[/dim]",
            f"[green]{stats.running_count} running[/green]" if stats.running_count else "[dim]0 running[/dim]",
            f"[dim]{_fmt_tokens(stats.total_tokens)} tok[/dim]",
            f"[dim]${stats.total_cost_usd:.3f}[/dim]",
        ]
        stat_widget.update("  ".join(parts))

    def _repaint_filter_bar(self) -> None:
        status_filter = _STATUS_FILTERS[self._status_filter_idx]
        tool_filter = _TOOL_FILTERS[self._tool_filter_idx]
        hours = _HOURS_OPTIONS[self._hours_idx]
        visible = self._visible_sessions()

        sf_label = status_filter or "ALL"
        tf_label = tool_filter or "ALL"
        h_label = f"{hours:.0f}h"

        parts = [
            f"  [bold #00d7ff]F[/bold #00d7ff]  [dim]status:[/dim] [cyan]{sf_label}[/cyan]",
            f"  [bold #00d7ff]T[/bold #00d7ff]  [dim]tool:[/dim] [cyan]{tf_label}[/cyan]",
            f"  [bold #00d7ff]H[/bold #00d7ff]  [dim]window:[/dim] [cyan]{h_label}[/cyan]",
            f"  [dim]{len(visible)} shown[/dim]",
        ]
        self.query_one("#dash-filter", Static).update("".join(parts))

    def _repaint_actions(self) -> None:
        lines = [
            f"  [bold #00d7ff]Enter[/bold #00d7ff]  [dim]open detail[/dim]",
            f"  [bold #00d7ff]A[/bold #00d7ff]      [dim]activity log[/dim]",
            f"  [bold #00d7ff]R[/bold #00d7ff]      [dim]refresh now[/dim]",
            f"  [bold #00d7ff]1-9[/bold #00d7ff]    [dim]quick jump[/dim]",
        ]
        self.query_one("#dash-actions", Static).update("  ".join(lines))

    def _repaint_status_bar(self) -> None:
        bar = self.query_one("#dash-status-bar", Static)
        if self._last_update is not None:
            ago = int(time.time() - self._last_update)
            ts = f"{ago}s ago"
        else:
            ts = "never"

        total = len(self._sessions)
        running = sum(1 for s in self._sessions if s.display_status == "RUNNING")
        port_str = f"dispatch @ localhost:{self.port}"

        if self._server_online:
            bar.update(
                f"[dim]{port_str}  |  {total} sessions  |  {running} running"
                f"  |  updated: {ts}[/dim]"
            )
        else:
            bar.update(
                f"[red]dispatch OFFLINE (port {self.port})[/red]"
                f"  [dim]|  last seen: {ts}[/dim]"
            )

    # ── Keyboard actions ───────────────────────────────────────────────────────

    def action_cursor_down(self) -> None:
        self.query_one("#agents-table", DataTable).action_cursor_down()

    def action_cursor_up(self) -> None:
        self.query_one("#agents-table", DataTable).action_cursor_up()

    def action_jump_row(self, row: int) -> None:
        table = self.query_one("#agents-table", DataTable)
        target = row - 1
        if 0 <= target < table.row_count:
            table.move_cursor(row=target)

    def action_refresh_now(self) -> None:
        self.refresh_data()

    def action_cycle_status_filter(self) -> None:
        self._status_filter_idx = (self._status_filter_idx + 1) % len(_STATUS_FILTERS)
        self._repaint_table()
        self._repaint_filter_bar()

    def action_cycle_tool_filter(self) -> None:
        self._tool_filter_idx = (self._tool_filter_idx + 1) % len(_TOOL_FILTERS)
        self._repaint_table()
        self._repaint_filter_bar()

    def action_cycle_hours(self) -> None:
        self._hours_idx = (self._hours_idx + 1) % len(_HOURS_OPTIONS)
        self.hours = _HOURS_OPTIONS[self._hours_idx]
        self.refresh_data()

    def action_select_session(self) -> None:
        table = self.query_one("#agents-table", DataTable)
        cursor_row = table.cursor_row
        visible = self._visible_sessions()
        if cursor_row is None or cursor_row >= len(visible):
            return
        session = visible[cursor_row]
        from rover.screens.detail import DetailScreen
        self.app.push_screen(DetailScreen(session_id=session.session_id, port=self.port))

    def action_open_activity(self) -> None:
        try:
            from rover.screens.activity import ActivityScreen
            self.app.push_screen(ActivityScreen(port=self.port))
        except ImportError:
            pass
