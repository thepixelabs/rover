"""DetailScreen — live single-session view for rover.

Accepts a session_id and re-fetches the session from /api/state on a timer
so the detail stays fresh while the agent is running.  Refresh cadence:
  • RUNNING / APPROVAL  → every 3 s
  • anything else       → every 15 s

Pressing 'r' forces an immediate refresh.
Pressing 'a' opens the activity log filtered to this session.
"""

from __future__ import annotations

import time
from datetime import datetime
from typing import Optional

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Label, RichLog, Static

from rover.api import Session, fetch_single_session
from rover.menu import _fmt_tokens, _now_str

# ── Constants ──────────────────────────────────────────────────────────────────

_STATUS_COLOURS: dict[str, str] = {
    "RUNNING":  "green",
    "APPROVAL": "yellow",
    "WAITING":  "dim",
    "IDLE":     "dim",
    "ERROR":    "red",
}

_LIVE_STATES = {"RUNNING", "APPROVAL"}
_FAST_REFRESH_S = 3.0
_SLOW_REFRESH_S = 15.0


# ── Helpers ────────────────────────────────────────────────────────────────────

def _colour_status(status: str) -> str:
    colour = _STATUS_COLOURS.get(status, "white")
    return f"[{colour}]{status}[/{colour}]"


def _fmt_ts(epoch_ms: int) -> str:
    if not epoch_ms:
        return "—"
    dt = datetime.fromtimestamp(epoch_ms / 1000)
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def _fmt_relative(seconds: float) -> str:
    s = int(abs(seconds))
    if s < 60:
        return f"{s}s ago"
    if s < 3600:
        return f"{s // 60}m {s % 60}s ago"
    return f"{s // 3600}h {(s % 3600) // 60}m ago"


def _micro_state_label(micro_state: str, active_tool: Optional[str]) -> str:
    if micro_state == "tool_use" and active_tool:
        return f"[cyan]tool_use[/cyan] → [bold]{active_tool}[/bold]"
    labels = {
        "thinking":   "[green]thinking…[/green]",
        "researching": "[green]researching…[/green]",
        "idle":       "[dim]idle[/dim]",
        "waiting":    "[dim]waiting for input[/dim]",
        "approval":   "[yellow]awaiting approval[/yellow]",
        "error":      "[red]error[/red]",
    }
    return labels.get(micro_state, f"[dim]{micro_state}[/dim]")


# ── Screen ─────────────────────────────────────────────────────────────────────

class DetailScreen(Screen):
    """Live detail view for a single agent session."""

    DEFAULT_CSS = """
    DetailScreen {
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

    #detail-outer {
        width: 100%;
        height: auto;
        border: solid #404060;
        padding: 0 1;
        margin: 0;
    }

    #detail-header-row {
        height: 1;
        layout: horizontal;
    }

    #detail-title {
        width: 1fr;
        color: #00d7ff;
        text-style: bold;
    }

    #detail-clock {
        width: auto;
        color: #505070;
    }

    .detail-divider {
        color: #404060;
        height: 1;
        margin-bottom: 0;
    }

    .section-heading {
        text-style: bold;
        color: #c0c0e0;
        height: 1;
        margin-top: 1;
        padding: 0;
    }

    .meta-row {
        height: 1;
        layout: horizontal;
        margin-bottom: 0;
    }

    .meta-key {
        width: 18;
        color: #505070;
    }

    .meta-value {
        width: 1fr;
    }

    #detail-preview {
        height: auto;
        max-height: 20;
        border: solid #1a1a3a;
        padding: 0 1;
        margin-top: 0;
        background: #0a0a14;
    }

    #detail-hint-bar {
        height: 1;
        dock: bottom;
        background: #1a1a3a;
        color: #808080;
    }

    #detail-live-badge {
        height: 1;
        color: #505070;
        text-align: right;
    }
    """

    BINDINGS = [
        Binding("escape", "back", "Back"),
        Binding("q", "back", "Back"),
        Binding("r", "refresh_now", "Refresh"),
        Binding("a", "open_activity", "Activity"),
    ]

    def __init__(self, session_id: str, port: int = 4242, **kwargs) -> None:
        super().__init__(**kwargs)
        self.session_id = session_id
        self.port = port
        self._session: Optional[Session] = None
        self._server_online: bool = False
        self._last_update: Optional[float] = None
        self._refresh_timer = None

    # ── Composition ────────────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        with Vertical(id="detail-outer"):
            with Horizontal(id="detail-header-row"):
                yield Label("SESSION DETAIL", id="detail-title")
                yield Label(_now_str(), id="detail-clock")
            yield Static("─" * 60, classes="detail-divider")
            yield Static("", id="detail-meta")
            yield Static("", id="detail-tokens")
            yield Static("", id="detail-activity-section")
            yield Static("", id="detail-live-badge")
        yield Static("", id="detail-hint-bar")

    def on_mount(self) -> None:
        self._fetch_and_repaint()
        self.set_interval(1.0, self._tick_clock)
        self._refresh_timer = self.set_interval(_FAST_REFRESH_S, self._auto_refresh)

    # ── Tick ───────────────────────────────────────────────────────────────────

    def _tick_clock(self) -> None:
        self.query_one("#detail-clock", Label).update(_now_str())
        if self._session is not None:
            self._repaint_live_badge()

    # ── Data refresh ───────────────────────────────────────────────────────────

    def _fetch_and_repaint(self) -> None:
        import threading

        def _fetch() -> None:
            session, online = fetch_single_session(
                port=self.port, session_id=self.session_id
            )
            self.call_from_thread(self._apply_data, session, online)

        threading.Thread(target=_fetch, daemon=True).start()

    def _auto_refresh(self) -> None:
        self._fetch_and_repaint()

    def _apply_data(self, session: Optional[Session], online: bool) -> None:
        self._session = session
        self._server_online = online
        self._last_update = time.time()
        self._repaint_all()

    # ── Repainting ─────────────────────────────────────────────────────────────

    def _repaint_all(self) -> None:
        s = self._session
        if s is None:
            self.query_one("#detail-meta", Static).update(
                "[red]Session not found[/red]  (may have ended)"
                if self._server_online else
                "[red]dispatch server offline[/red]"
            )
            self.query_one("#detail-tokens", Static).update("")
            self.query_one("#detail-activity-section", Static).update("")
            self._repaint_hint_bar()
            return

        # ── Meta section ──────────────────────────────────────────────────────
        age_str      = _fmt_relative(s.age_seconds)
        started_str  = _fmt_ts(s.started_at)
        idle_str     = _fmt_relative(s.idle_seconds)
        cost_str     = f"${s.cost_usd:.4f}"

        meta_lines = [
            f"[dim]{'Project':<18}[/dim]{s.project_name or '—'}",
            f"[dim]{'Session ID':<18}[/dim][dim]{s.session_id}[/dim]",
            f"[dim]{'Tool':<18}[/dim]{s.tool or '—'}",
            f"[dim]{'Status':<18}[/dim]{_colour_status(s.display_status)}",
            f"[dim]{'Micro state':<18}[/dim]{_micro_state_label(s.micro_state, s.active_tool)}",
            f"[dim]{'Model':<18}[/dim]{s.model or '—'}",
            f"[dim]{'Branch':<18}[/dim]{s.git_branch or '—'}",
            f"[dim]{'Started':<18}[/dim]{age_str}  ({started_str})",
            f"[dim]{'Last active':<18}[/dim]{idle_str}",
            f"[dim]{'Turns':<18}[/dim]{s.turn_count}",
            f"[dim]{'Cost':<18}[/dim]{cost_str}",
        ]
        self.query_one("#detail-meta", Static).update("\n".join(meta_lines))

        # ── Token breakdown ───────────────────────────────────────────────────
        tok_total = s.total_tokens
        tok_lines = [
            "",
            "[bold #c0c0e0]TOKEN USAGE[/bold #c0c0e0]",
            "─" * 24,
            f"[dim]{'Input':<18}[/dim]{_fmt_tokens(s.token_input):>8}",
            f"[dim]{'Output':<18}[/dim]{_fmt_tokens(s.token_output):>8}",
            f"[dim]{'Cache read':<18}[/dim]{_fmt_tokens(s.token_cache_read):>8}",
            f"[dim]{'Cache write':<18}[/dim]{_fmt_tokens(s.token_cache_write):>8}",
            "─" * 24,
            f"[dim]{'Total':<18}[/dim][bold]{_fmt_tokens(tok_total):>8}[/bold]",
        ]
        self.query_one("#detail-tokens", Static).update("\n".join(tok_lines))

        # ── Task preview ──────────────────────────────────────────────────────
        preview = (s.prompt_preview or "").strip()
        if not preview:
            preview = "[dim](no task preview)[/dim]"
        activity_lines = [
            "",
            "[bold #c0c0e0]TASK PREVIEW[/bold #c0c0e0]",
            "─" * 12,
            preview,
        ]
        self.query_one("#detail-activity-section", Static).update(
            "\n".join(activity_lines)
        )

        self._repaint_live_badge()
        self._repaint_hint_bar()

    def _repaint_live_badge(self) -> None:
        s = self._session
        badge = self.query_one("#detail-live-badge", Static)
        if s is None:
            badge.update("")
            return
        if s.display_status in _LIVE_STATES:
            idle_s = int(s.idle_seconds)
            badge.update(
                f"[green]● LIVE[/green]  [dim]last activity {idle_s}s ago"
                f"  |  auto-refresh {_FAST_REFRESH_S:.0f}s[/dim]"
            )
        else:
            if self._last_update:
                ago = int(time.time() - self._last_update)
                badge.update(f"[dim]last refresh {ago}s ago[/dim]")
            else:
                badge.update("")

    def _repaint_hint_bar(self) -> None:
        hint = self.query_one("#detail-hint-bar", Static)
        hint.update(
            "[dim][bold #00d7ff]q/Esc[/bold #00d7ff] back"
            "  [bold #00d7ff]r[/bold #00d7ff] refresh"
            "  [bold #00d7ff]a[/bold #00d7ff] activity log[/dim]"
        )

    # ── Keyboard actions ───────────────────────────────────────────────────────

    def action_back(self) -> None:
        self.app.pop_screen()

    def action_refresh_now(self) -> None:
        self._fetch_and_repaint()

    def action_open_activity(self) -> None:
        try:
            from rover.screens.activity import ActivityScreen
            self.app.push_screen(
                ActivityScreen(port=self.port, session_id=self.session_id)
            )
        except ImportError:
            pass
