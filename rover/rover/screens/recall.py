"""RecallScreen — conversation history picker for rover.

Shows all conversations discovered by sessions_index.list_altergo_sessions()
and lets the user resume one via --yolo-resume=<UUID>.

Keybindings
-----------
  ↑/↓ / j/k   navigate rows
  /            focus search input; live-filters by project + topic
  f            cycle provider filter: all → claude → gemini → codex → copilot → all
  s            cycle sort: time (default) → project → provider
  Enter        resume selected conversation
  I            open session-ID input modal, then resume by raw UUID
  Escape       close screen and return to menu
"""

from __future__ import annotations

import threading
import time
from typing import Optional

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen, Screen
from textual.widgets import DataTable, Input, Label, Static

from rover.sessions_index import SessionRecord, list_altergo_sessions


# ── Constants ──────────────────────────────────────────────────────────────────

_PROVIDER_BADGE: dict[str, str] = {
    "claude":  "[bold blue]claude[/bold blue]",
    "gemini":  "[bold green]gemini[/bold green]",
    "codex":   "[bold yellow]codex[/bold yellow]",
    "copilot": "[bold cyan]copilot[/bold cyan]",
}

_PROVIDER_FILTERS: list[Optional[str]] = [
    None, "claude", "gemini", "codex", "copilot"
]

_SORT_CYCLES: list[str] = ["time", "project", "provider"]

_PROJECT_MAX = 14
_PREVIEW_COLS = 80   # gets most of the terminal width


# ── Helpers ────────────────────────────────────────────────────────────────────

def _provider_badge(provider: str) -> str:
    return _PROVIDER_BADGE.get(provider.lower(), f"[dim]{provider[:6]}[/dim]")


def _source_col(provider: str, project_path: str) -> str:
    """Compact 'provider  project' cell — fits ~22 chars."""
    badge = _provider_badge(provider)
    if not project_path:
        return badge
    import pathlib
    name = pathlib.Path(project_path).name or project_path
    if len(name) > _PROJECT_MAX:
        name = name[: _PROJECT_MAX - 1] + "…"
    return f"{badge}  [dim]{name}[/dim]"


def _time_ago(epoch: float) -> str:
    """Return a compact human-readable age string: '2m', '1h', '3d'."""
    delta = time.time() - epoch
    if delta < 0:
        return "0s"
    if delta < 60:
        return f"{int(delta)}s"
    if delta < 3600:
        return f"{int(delta / 60)}m"
    if delta < 86400:
        return f"{int(delta / 3600)}h"
    return f"{int(delta / 86400)}d"


def _topic_col(preview: str, max_len: int = _PREVIEW_COLS) -> str:
    if not preview:
        return "[dim](no topic)[/dim]"
    text = preview.replace("\n", " ").strip()
    if len(text) > max_len:
        return text[: max_len - 1] + "…"
    return text


# ── Session-ID input modal ─────────────────────────────────────────────────────

class _SessionIdModal(ModalScreen):
    """Small modal: prompt for a raw session ID to resume."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", show=False),
        Binding("ctrl+c", "cancel", "Cancel", show=False),
    ]

    DEFAULT_CSS = """
    _SessionIdModal {
        align: center middle;
    }

    #sid-box {
        width: 90%;
        min-width: 40;
        max-width: 80;
        height: auto;
        overflow-x: hidden;
        border: solid #404060;
        padding: 1 2;
        background: #0d0d1a;
    }

    #sid-title {
        text-style: bold;
        color: #00d7ff;
        margin-bottom: 1;
    }

    #sid-divider {
        color: #404060;
        margin-bottom: 1;
    }

    #sid-hint-label {
        color: #505070;
        height: 1;
        margin-bottom: 1;
    }

    #sid-input {
        width: 100%;
        margin-bottom: 1;
    }

    #sid-hint {
        color: #606080;
        height: 1;
    }
    """

    def compose(self) -> ComposeResult:
        with Vertical(id="sid-box"):
            yield Label("Resume by session ID", id="sid-title")
            yield Label("─" * 40, id="sid-divider")
            yield Label("Enter session ID (UUID):", id="sid-hint-label")
            yield Input(placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
                        id="sid-input")
            yield Label("[dim]Enter confirm  ·  Esc cancel[/dim]", id="sid-hint")

    def on_mount(self) -> None:
        self.query_one("#sid-input", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        value = event.value.strip()
        if value:
            self.dismiss(value)
        else:
            self.dismiss(None)

    def action_cancel(self) -> None:
        self.dismiss(None)


# ── RecallScreen ───────────────────────────────────────────────────────────────

class RecallScreen(Screen):
    """Cross-account session picker: browse, filter, sort, and resume."""

    BINDINGS = [
        Binding("escape",   "close_screen",  "Back",     show=False),
        Binding("j",        "cursor_down",   "Down",     show=False),
        Binding("k",        "cursor_up",     "Up",       show=False),
        Binding("down",     "cursor_down",   "Down",     show=False),
        Binding("up",       "cursor_up",     "Up",       show=False),
        Binding("enter",    "resume_session","Resume",   show=False),
        Binding("/",        "focus_search",  "Search",   show=False),
        Binding("f",        "cycle_provider","Provider", show=False),
        Binding("s",        "cycle_sort",    "Sort",     show=False),
        Binding("I",        "session_id_input", "By ID", show=False),
    ]

    DEFAULT_CSS = """
    RecallScreen {
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

    #recall-box {
        width: 100%;
        height: auto;
        border: solid #404060;
        padding: 0 1;
        margin: 0;
    }

    #recall-header {
        height: 1;
        layout: horizontal;
    }

    #recall-title {
        width: 1fr;
        color: #00d7ff;
        text-style: bold;
    }

    #recall-count {
        width: auto;
        color: #505070;
        content-align: right middle;
    }

    #recall-search {
        width: 100%;
        margin-top: 0;
        margin-bottom: 0;
        display: none;
    }

    #recall-search.visible {
        display: block;
    }

    #recall-filter-bar {
        height: 1;
        color: #404060;
    }

    #recall-table {
        height: auto;
        border: none;
        padding: 0;
        margin: 0;
        background: #0d0d1a;
        scrollbar-size: 0 0;
    }

    #recall-table > .datatable--header {
        background: #1a1a3a;
        color: #00d7ff;
    }

    #recall-table > .datatable--cursor {
        background: #1a2a3a;
        color: #ffffff;
    }

    #recall-loading {
        height: 1;
        color: #505070;
        content-align: center middle;
    }

    #recall-hint {
        height: 1;
        dock: bottom;
        background: #1a1a3a;
        color: #808080;
    }
    """

    def __init__(self) -> None:
        super().__init__()
        self._all_sessions: list[SessionRecord] = []
        self._provider_idx: int = 0
        self._sort_idx: int = 0
        self._search_text: str = ""
        self._loading: bool = True

    # ── Composition ────────────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        with Vertical(id="recall-box"):
            with Horizontal(id="recall-header"):
                yield Label("RECALL CONVERSATION", id="recall-title")
                yield Label("", id="recall-count")
            yield Input(placeholder="  filter by project or topic…",
                        id="recall-search")
            yield Static("", id="recall-filter-bar")
            yield Static("[dim]loading sessions…[/dim]", id="recall-loading")
            yield DataTable(id="recall-table", show_cursor=True)
        yield Static("", id="recall-hint")

    def on_mount(self) -> None:
        table = self.query_one("#recall-table", DataTable)
        table.add_columns("SOURCE", "AGE", "TOPIC")
        table.cursor_type = "row"
        self._repaint_filter_bar()
        self._repaint_hint()
        # Load sessions in background thread so the screen draws immediately.
        t = threading.Thread(target=self._load_sessions, daemon=True)
        t.start()

    # ── Background load ────────────────────────────────────────────────────────

    def _load_sessions(self) -> None:
        sessions = list_altergo_sessions()
        self.call_from_thread(self._apply_sessions, sessions)

    def _apply_sessions(self, sessions: list[SessionRecord]) -> None:
        self._all_sessions = sessions
        self._loading = False
        loading_widget = self.query_one("#recall-loading", Static)
        loading_widget.display = False
        self._repaint_table()
        self._repaint_filter_bar()
        # Focus the table after load so arrow keys work immediately.
        self.query_one("#recall-table", DataTable).focus()

    # ── Filtering / sorting ────────────────────────────────────────────────────

    def _visible_sessions(self) -> list[SessionRecord]:
        provider_filter = _PROVIDER_FILTERS[self._provider_idx]
        result = self._all_sessions

        if provider_filter is not None:
            result = [s for s in result if s.provider.lower() == provider_filter]

        if self._search_text:
            needle = self._search_text.lower()
            result = [
                s for s in result
                if needle in (s.project_path or "").lower()
                or needle in (s.preview or "").lower()
                or needle in (s.account or "").lower()
            ]

        sort_key = _SORT_CYCLES[self._sort_idx]
        if sort_key == "time":
            result = sorted(result, key=lambda s: s.modified_at, reverse=True)
        elif sort_key == "project":
            result = sorted(result, key=lambda s: (s.project_path or "").lower())
        elif sort_key == "provider":
            result = sorted(result, key=lambda s: s.provider.lower())

        return result

    # ── Repaint ────────────────────────────────────────────────────────────────

    def _repaint_table(self) -> None:
        table = self.query_one("#recall-table", DataTable)
        table.clear()
        visible = self._visible_sessions()

        for record in visible:
            source = _source_col(record.provider, record.project_path)
            age = _time_ago(record.modified_at)
            topic = _topic_col(record.preview)
            table.add_row(source, age, topic, key=record.session_id)

        count_label = self.query_one("#recall-count", Label)
        total = len(self._all_sessions)
        shown = len(visible)
        if shown == total:
            count_label.update(f"[dim]{total} conversations[/dim]")
        else:
            count_label.update(f"[dim]{shown}/{total} shown[/dim]")

    def _repaint_filter_bar(self) -> None:
        provider_filter = _PROVIDER_FILTERS[self._provider_idx]
        sort_key = _SORT_CYCLES[self._sort_idx]
        pf_label = provider_filter or "all"
        parts = [
            f"  [bold #00d7ff]F[/bold #00d7ff]  [dim]provider:[/dim] [cyan]{pf_label}[/cyan]",
            f"  [bold #00d7ff]S[/bold #00d7ff]  [dim]sort:[/dim] [cyan]{sort_key}[/cyan]",
            f"  [bold #00d7ff]/[/bold #00d7ff]  [dim]search[/dim]",
        ]
        self.query_one("#recall-filter-bar", Static).update("".join(parts))

    def _repaint_hint(self) -> None:
        parts = [
            "[dim]↑↓/jk navigate",
            "· Enter resume",
            "· I by ID",
            "· F provider",
            "· S sort",
            "· / search",
            "· Esc back[/dim]",
        ]
        self.query_one("#recall-hint", Static).update("  ".join(parts))

    # ── Search input ───────────────────────────────────────────────────────────

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "recall-search":
            self._search_text = event.value.strip()
            self._repaint_table()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "recall-search":
            # Return focus to the table so Enter resumes the selected row.
            self.query_one("#recall-table", DataTable).focus()

    # ── Keyboard actions ───────────────────────────────────────────────────────

    def action_close_screen(self) -> None:
        self.app.pop_screen()

    def action_cursor_down(self) -> None:
        self.query_one("#recall-table", DataTable).action_cursor_down()

    def action_cursor_up(self) -> None:
        self.query_one("#recall-table", DataTable).action_cursor_up()

    def action_focus_search(self) -> None:
        search = self.query_one("#recall-search", Input)
        search.add_class("visible")
        search.focus()

    def action_cycle_provider(self) -> None:
        self._provider_idx = (self._provider_idx + 1) % len(_PROVIDER_FILTERS)
        self._repaint_table()
        self._repaint_filter_bar()

    def action_cycle_sort(self) -> None:
        self._sort_idx = (self._sort_idx + 1) % len(_SORT_CYCLES)
        self._repaint_table()
        self._repaint_filter_bar()

    def action_resume_session(self) -> None:
        if self._loading:
            return
        table = self.query_one("#recall-table", DataTable)
        cursor_row = table.cursor_row
        visible = self._visible_sessions()
        if cursor_row is None or cursor_row >= len(visible):
            return
        record = visible[cursor_row]
        self._launch(record.session_id, record)

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Intercept Enter from within the DataTable widget."""
        event.stop()
        self.action_resume_session()

    def action_session_id_input(self) -> None:
        """Prompt for a raw session ID, then resume it."""
        def _on_id(session_id: str | None) -> None:
            if not session_id:
                return
            # Try to find the matching record so we can supply project/account.
            matched = next(
                (s for s in self._all_sessions if s.session_id == session_id),
                None,
            )
            self._launch(session_id, matched)

        self.app.push_screen(_SessionIdModal(), callback=_on_id)

    # ── Launch ─────────────────────────────────────────────────────────────────

    def _launch(
        self,
        session_id: str,
        record: SessionRecord | None,
    ) -> None:
        """Exit the Textual app so run_menu()'s loop can call _exec_altergo."""
        payload: dict = {
            "action": "recall_resume",
            "session_id": session_id,
        }
        if record is not None:
            payload["account"] = record.account
            payload["provider"] = record.provider
            payload["project_path"] = record.project_path
        self.app.exit(result=payload)
