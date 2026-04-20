"""Detail screen for rover.

Full-screen view of a single agent session.  Accepts a Session object at
construction time and renders all available metadata using Rich markup.
Press q or Escape to return to the previous screen.
"""

from __future__ import annotations

from datetime import datetime

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Label, Static

from rover.api import Session

# ── Status colour map (consistent with dashboard.py) ─────────────────────────

_STATUS_COLOURS: dict[str, str] = {
    "RUNNING":  "green",
    "APPROVAL": "yellow",
    "WAITING":  "dim",
    "IDLE":     "dim",
    "ERROR":    "red",
}

_TASK_PREVIEW_MAX_LINES = 20


def _colour_status(status: str) -> str:
    colour = _STATUS_COLOURS.get(status, "white")
    return f"[{colour}]{status}[/{colour}]"


def _fmt_ts(epoch_ms: int) -> str:
    """Format an epoch-millisecond timestamp as 'YYYY-MM-DD HH:MM'."""
    if not epoch_ms:
        return "—"
    dt = datetime.fromtimestamp(epoch_ms / 1000)
    return dt.strftime("%Y-%m-%d %H:%M")


def _fmt_relative(seconds: float) -> str:
    """Human-readable elapsed time: '4s', '3m ago', '1h 12m ago'."""
    s = int(seconds)
    if s < 60:
        return f"{s}s ago"
    if s < 3600:
        return f"{s // 60}m ago"
    return f"{s // 3600}h {(s % 3600) // 60}m ago"


def _truncate_preview(text: str, max_lines: int) -> str:
    lines = text.splitlines()
    if len(lines) <= max_lines:
        return text
    return "\n".join(lines[:max_lines]) + "\n…"


class DetailScreen(Screen):
    """Full-screen detail view for a single agent session."""

    BINDINGS = [
        Binding("escape", "back", "Back"),
        Binding("q", "back", "Back"),
    ]

    DEFAULT_CSS = """
    DetailScreen {
        align: center top;
        padding: 1 2;
    }

    #detail-container {
        width: 80%;
        height: auto;
        border: solid $primary;
        padding: 1 2;
    }

    #detail-header {
        layout: horizontal;
        height: 1;
        margin-bottom: 0;
    }

    #detail-title {
        text-style: bold;
        color: $primary;
        width: 1fr;
    }

    #detail-hint {
        color: $text-muted;
        content-align: right middle;
    }

    .divider {
        color: $primary-darken-2;
        margin-bottom: 1;
    }

    .meta-row {
        height: 1;
        layout: horizontal;
        margin-bottom: 0;
    }

    .meta-key {
        width: 16;
        color: $text-muted;
    }

    .meta-value {
        width: 1fr;
    }

    .section-heading {
        text-style: bold;
        color: $secondary;
        margin-top: 1;
        margin-bottom: 0;
    }

    .section-divider {
        color: $primary-darken-2;
        margin-bottom: 1;
    }

    #task-preview {
        margin-top: 0;
        color: $text;
    }
    """

    def __init__(self, session: Session, **kwargs) -> None:
        super().__init__(**kwargs)
        self.session = session

    def compose(self) -> ComposeResult:
        s = self.session

        age_str = _fmt_relative(s.age_seconds)
        started_str = _fmt_ts(s.started_at)
        idle_str = _fmt_relative(s.idle_seconds)
        cost_str = f"${s.cost_usd:.4f}"
        coloured_status = _colour_status(s.display_status)

        branch_display = s.git_branch if s.git_branch else "—"
        model_display = s.model if s.model else "—"
        active_tool_display = s.active_tool if s.active_tool else "—"

        with Vertical(id="detail-container"):
            with Horizontal(id="detail-header"):
                yield Static("SESSION DETAIL", id="detail-title")
                yield Static("[dim]\\[q/Esc] back[/dim]", id="detail-hint")

            yield Static("─" * 60, classes="divider")

            # Core session metadata
            with Horizontal(classes="meta-row"):
                yield Label("Project:", classes="meta-key")
                yield Static(s.project_name or "—", classes="meta-value")

            with Horizontal(classes="meta-row"):
                yield Label("Session ID:", classes="meta-key")
                yield Static(s.session_id or "—", classes="meta-value")

            with Horizontal(classes="meta-row"):
                yield Label("Tool:", classes="meta-key")
                yield Static(s.tool or "—", classes="meta-value")

            with Horizontal(classes="meta-row"):
                yield Label("Status:", classes="meta-key")
                yield Static(coloured_status, classes="meta-value", markup=True)

            with Horizontal(classes="meta-row"):
                yield Label("Model:", classes="meta-key")
                yield Static(model_display, classes="meta-value")

            with Horizontal(classes="meta-row"):
                yield Label("Branch:", classes="meta-key")
                yield Static(branch_display, classes="meta-value")

            with Horizontal(classes="meta-row"):
                yield Label("Started:", classes="meta-key")
                yield Static(
                    f"{age_str} ({started_str})", classes="meta-value"
                )

            with Horizontal(classes="meta-row"):
                yield Label("Last active:", classes="meta-key")
                yield Static(idle_str, classes="meta-value")

            with Horizontal(classes="meta-row"):
                yield Label("Cost:", classes="meta-key")
                yield Static(cost_str, classes="meta-value")

            with Horizontal(classes="meta-row"):
                yield Label("Turns:", classes="meta-key")
                yield Static(str(s.turn_count), classes="meta-value")

            # Current activity section
            yield Static("CURRENT ACTIVITY", classes="section-heading")
            yield Static("─" * 16, classes="section-divider")

            with Horizontal(classes="meta-row"):
                yield Label("Tool:", classes="meta-key")
                yield Static(active_tool_display, classes="meta-value")

            # Task preview section
            yield Static("TASK PREVIEW", classes="section-heading")
            yield Static("─" * 12, classes="section-divider")

            if s.prompt_preview:
                preview_text = _truncate_preview(s.prompt_preview, _TASK_PREVIEW_MAX_LINES)
            else:
                preview_text = "[dim](no task preview available)[/dim]"

            yield Static(preview_text, id="task-preview", markup=True)

    def action_back(self) -> None:
        """Return to the previous screen."""
        self.app.pop_screen()
