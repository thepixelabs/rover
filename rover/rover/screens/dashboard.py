"""DashboardScreen — the main view for rover.

Shows a DataTable of agent sessions (fetched from the dispatch HTTP API)
and a compact tmux session summary beneath it, plus a one-line status bar
docked to the bottom of the screen.
"""

from __future__ import annotations

import time
from typing import Optional

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import DataTable, Label, Static

from rover.api import Session, fetch_state

# ── Constants ──────────────────────────────────────────────────────────────────

_TASK_MAX_LEN = 35

# Rich markup for display_status values
_STATUS_MARKUP: dict[str, str] = {
    "RUNNING":  "[green]RUNNING  [/]",
    "APPROVAL": "[yellow]APPROVAL [/]",
    "WAITING":  "[dim]WAITING  [/]",
    "IDLE":     "[dim]IDLE     [/]",
    "ERROR":    "[red]ERROR    [/]",
}

# Rich markup for tool badge values
_TOOL_MARKUP: dict[str, str] = {
    "claude":  "[cyan]claude[/]",
    "gemini":  "[blue]gemini[/]",
    "codex":   "[magenta]codex[/]",
    "copilot": "[yellow]copilot[/]",
}


# ── Helpers ────────────────────────────────────────────────────────────────────

def _status_markup(status: str) -> str:
    return _STATUS_MARKUP.get(status, status)


def _tool_markup(tool: str) -> str:
    key = tool.lower()
    return _TOOL_MARKUP.get(key, tool)


def _task_text(session: Session) -> str:
    """Return the task column text for a session."""
    if session.micro_state == "tool_use" and session.active_tool:
        raw = session.active_tool
    else:
        raw = (session.prompt_preview or "").replace("\n", " ").strip()

    if len(raw) > _TASK_MAX_LEN:
        return raw[:_TASK_MAX_LEN - 1] + "\u2026"
    return raw


def _elapsed_ago(epoch_seconds: float) -> str:
    """Return how many seconds ago an epoch timestamp was."""
    delta = int(time.time() - epoch_seconds)
    if delta < 0:
        return "0s"
    if delta < 60:
        return f"{delta}s"
    if delta < 3600:
        return f"{delta // 60}m"
    return f"{delta // 3600}h{(delta % 3600) // 60}m"


# ── Screen ─────────────────────────────────────────────────────────────────────

class DashboardScreen(Screen):
    """Main dashboard: agent sessions + tmux overview."""

    BINDINGS = [
        Binding("j", "cursor_down", "Down", show=False),
        Binding("k", "cursor_up", "Up", show=False),
        Binding("enter", "select_session", "Open detail", show=False),
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

        # Mutable state updated on every refresh
        self._sessions: list[Session] = []
        self._server_online: bool = False
        self._last_update: Optional[float] = None

    # ── Composition ────────────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        yield Label("", id="agents-header", classes="panel-title")
        yield DataTable(id="sessions-table", show_cursor=True)
        yield Static("", id="status-bar")

    def on_mount(self) -> None:
        table = self.query_one("#sessions-table", DataTable)
        table.add_columns("#", "STATUS", "TOOL", "TASK", "ELAPSED")
        self.refresh_data()
        table.focus()

    # ── Data refresh ───────────────────────────────────────────────────────────

    def refresh_data(self) -> None:
        """Fetch fresh data from the dispatch server and repaint all widgets."""
        sessions, online = fetch_state(port=self.port, hours=self.hours)
        self._sessions = sessions
        self._server_online = online
        self._last_update = time.time()

        self._repaint_table(sessions)
        self._repaint_status(sessions, online)

    def _repaint_table(self, sessions: list[Session]) -> None:
        table = self.query_one("#sessions-table", DataTable)
        table.clear()

        running_count = sum(1 for s in sessions if s.display_status == "RUNNING")
        queued_count = sum(
            1 for s in sessions if s.display_status in ("WAITING", "APPROVAL")
        )
        header = self.query_one("#agents-header", Label)
        header.update(
            f"AGENTS  (last {self.hours:.0f}h \u00b7 {running_count} running"
            f" \u00b7 {queued_count} queued)      [dim]\\[r] refresh[/dim]"
        )

        for idx, session in enumerate(sessions, start=1):
            row_num = str(idx)
            status_cell = _status_markup(session.display_status)
            tool_cell = _tool_markup(session.tool)
            task_cell = _task_text(session)
            elapsed_cell = session.format_age()
            table.add_row(row_num, status_cell, tool_cell, task_cell, elapsed_cell)

    def _repaint_status(self, sessions: list[Session], online: bool) -> None:
        status_bar = self.query_one("#status-bar", Static)

        if self._last_update is not None:
            last_update_ago = int(time.time() - self._last_update)
            last_update_str = f"{last_update_ago}s ago"
        else:
            last_update_str = "never"

        running_count = sum(1 for s in sessions if s.display_status == "RUNNING")
        total = len(sessions)

        if online:
            text = (
                f"dispatch @ localhost:{self.port}"
                f"  |  {total} sessions"
                f"  |  {running_count} running"
                f"  |  last update: {last_update_str}"
            )
        else:
            text = (
                f"[red]dispatch OFFLINE (port {self.port})[/red]"
                f"  |  last seen: {last_update_str}"
            )

        status_bar.update(text)

    # ── Keyboard actions ───────────────────────────────────────────────────────

    def action_cursor_down(self) -> None:
        self.query_one("#sessions-table", DataTable).action_cursor_down()

    def action_cursor_up(self) -> None:
        self.query_one("#sessions-table", DataTable).action_cursor_up()

    def action_jump_row(self, row: int) -> None:
        table = self.query_one("#sessions-table", DataTable)
        target = row - 1  # 0-indexed
        if 0 <= target < table.row_count:
            table.move_cursor(row=target)

    def action_select_session(self) -> None:
        table = self.query_one("#sessions-table", DataTable)
        cursor_row = table.cursor_row
        if cursor_row is None or cursor_row >= len(self._sessions):
            return

        session = self._sessions[cursor_row]
        try:
            from rover.screens.detail import DetailScreen

            self.app.push_screen(DetailScreen(session=session))
        except ImportError:
            # detail screen not yet available (sibling agent not yet done)
            pass
