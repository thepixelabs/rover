"""Main menu — Textual-based session list with single-keypress input.

This is the PRIMARY entry-point UI for rover.  It renders with Textual
(not Raw-mode Rich) so the refresh cycle is event-driven and never blocks
on a manual select.select() timeout.

Flow:
  run_menu(config, hours) → MenuAction

  The Textual app runs until the user presses a key that maps to one of:
    Q / Ctrl+C  → MenuAction.QUIT
    D           → MenuAction.DISPATCH
    S           → MenuAction.SETTINGS
    Enter / 1-9 → attach session (app exits with attach payload, caller
                  invokes session_manager.attach_session, re-enters menu)

  Subprocess-blocking flows (altergo launcher, server toggle) exit the
  app with a payload dict, let __main__'s while loop handle the subprocess,
  then re-enter run_menu.  This keeps the Textual event loop clean.

  Auto-refresh every 5 seconds via set_interval.
"""

from __future__ import annotations

import os
import threading
from datetime import datetime
from enum import Enum
from typing import Any

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen, Screen
from textual.widgets import DataTable, Input, Label, LoadingIndicator, Static

from rover import __version__
from rover.api import MenuStats, fetch_menu_stats
from rover.session_manager import (
    TmuxSession,
    kill_session,
    list_sessions,
)
from rover import caffeinate


# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------

class MenuAction(Enum):
    QUIT = "quit"
    DISPATCH = "dispatch"
    SETTINGS = "settings"


# ---------------------------------------------------------------------------
# Utility helpers  (kept from old impl; still used by the screens below)
# ---------------------------------------------------------------------------

def _fmt_tokens(n: int) -> str:
    """Format token count: 1234 → '1.2k', 1234567 → '1.2M'."""
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}k"
    return str(n)


def _now_str() -> str:
    return datetime.now().strftime("%a %b %d  %H:%M:%S")


def _figlet_renderable(
    font: str,
    text: str = "rover",
    width: int = 80,
    colors: list[str] | None = None,
):
    """Return a Rich Text object for the figlet header.

    Previous version returned a raw ANSI string + used `Static(..., markup=True)`,
    but markup=True tells Textual to parse Rich markup like `[bold]…[/bold]` —
    NOT ANSI escape codes. ANSI got displayed literally (you'd see `[0m`
    fragments and the figlet glyphs scattered across the screen).

    Text.from_ansi parses ANSI escapes into a proper Rich Text object that
    Textual renders with the correct colours and layout.

    ``colors`` lets callers override the default green gradient — useful for
    the small "rover" sub-label beneath a colored nickname where we want a
    distinct, bright-white look instead of more green-on-green.
    """
    from rich.text import Text
    try:
        from rich_pyfiglet import RichFiglet  # type: ignore[import]
        from io import StringIO
        from rich.console import Console
        fig = RichFiglet(
            text,
            font=font,
            colors=colors if colors is not None else [
                "#5fff87", "#00d75f", "#005f00",
            ],
            horizontal=True,
        )
        buf = StringIO()
        # Render at the terminal's width so long fonts don't wrap; Textual's
        # Static will clip if the terminal is narrower than the figlet.
        con = Console(
            file=buf, width=max(20, width), highlight=False,
            markup=False, no_color=False, force_terminal=True,
        )
        con.print(fig)
        return Text.from_ansi(buf.getvalue().rstrip("\n"))
    except Exception:
        return Text(text, style="bold #5fff87")


# ---------------------------------------------------------------------------
# Yolo submenu screen
# ---------------------------------------------------------------------------

class YoloSubmenuScreen(ModalScreen):
    """Inline yolo submenu — y/r/p/Esc.

    ModalScreen (not Screen) so key events route exclusively to this screen
    after push_screen — avoids a race where the first y after Y is delivered
    while the parent screen still holds focus.
    """

    BINDINGS = [
        Binding("escape", "cancel", "Back", show=False),
        Binding("q",      "cancel", "Back", show=False),
        Binding("y",      "yolo_new",    "Yolo new",    show=False),
        Binding("r",      "yolo_resume", "Resume last", show=False),
        Binding("p",      "yolo_pick",   "Pick",        show=False),
    ]

    DEFAULT_CSS = """
    YoloSubmenuScreen {
        align: center middle;
    }

    #yolo-box {
        width: 90%;
        min-width: 40;
        max-width: 80;
        height: auto;
        overflow-x: hidden;
        border: solid #404060;
        padding: 1 2;
        background: #0d0d1a;
    }

    #yolo-title {
        text-style: bold;
        color: #00d7ff;
        margin-bottom: 1;
    }

    #yolo-divider {
        color: #404060;
        margin-bottom: 1;
    }

    .yolo-row {
        height: 1;
        layout: horizontal;
    }

    .yolo-key {
        width: 5;
        color: #00d7ff;
        text-style: bold;
    }

    .yolo-label {
        color: #808080;
    }

    #yolo-hint {
        margin-top: 1;
        height: auto;
        color: #606080;
    }
    """

    def compose(self) -> ComposeResult:
        with Vertical(id="yolo-box"):
            yield Label(f"rover  v{__version__}", id="yolo-title")
            yield Label("─" * 38, id="yolo-divider")
            yield Label("YOLO  (skip confirm)", id="yolo-heading")
            yield Static("")
            with Horizontal(classes="yolo-row"):
                yield Label("y", classes="yolo-key")
                yield Label("yolo-new  pick project+account", classes="yolo-label")
            with Horizontal(classes="yolo-row"):
                yield Label("r", classes="yolo-key")
                yield Label("resume-last  last session --yolo-resume", classes="yolo-label")
            with Horizontal(classes="yolo-row"):
                yield Label("p", classes="yolo-key")
                yield Label("yolo-pick  cross-account session picker", classes="yolo-label")
            with Horizontal(classes="yolo-row"):
                yield Label("Esc", classes="yolo-key")
                yield Label("cancel", classes="yolo-label")
            yield Label("y new  ·  r resume-last  ·  p pick  ·  Esc cancel",
                        id="yolo-hint")

    def action_cancel(self) -> None:
        self.app.pop_screen()

    def action_yolo_new(self) -> None:
        self.app.exit(result={"action": "altergo", "yolo": True})

    def action_yolo_resume(self) -> None:
        self.app.exit(result={"action": "altergo_recall"})

    def action_yolo_pick(self) -> None:
        self.app.exit(result={"action": "yolo_pick"})


# ---------------------------------------------------------------------------
# Confirm / input modals — replace former _blocking helpers
# ---------------------------------------------------------------------------

_MODAL_CSS = """
ModalScreen {
    align: center middle;
}

#modal-box {
    width: 90%;
    min-width: 40;
    max-width: 80;
    height: auto;
    overflow-x: hidden;
    border: solid #404060;
    padding: 1 2;
    background: #0d0d1a;
}

#modal-title {
    text-style: bold;
    color: #00d7ff;
    margin-bottom: 1;
}

#modal-divider {
    color: #404060;
    margin-bottom: 1;
}

.modal-line {
    color: #c0c0e0;
    height: 1;
}

.modal-line.dim {
    color: #808080;
}

.modal-line.ok {
    color: green;
}

.modal-line.err {
    color: red;
}

#modal-hint {
    margin-top: 1;
    color: #606080;
}

#modal-input {
    margin-top: 1;
    margin-bottom: 1;
}

LoadingIndicator {
    height: 1;
    color: #00d7ff;
}
"""


class KillConfirmModalScreen(ModalScreen):
    """Confirm-kill modal — y/n on a single session."""

    BINDINGS = [
        Binding("y",      "confirm", "Yes",    show=False),
        Binding("n",      "cancel",  "No",     show=False),
        Binding("escape", "cancel",  "Cancel", show=False),
    ]

    DEFAULT_CSS = _MODAL_CSS

    def __init__(self, session_name: str) -> None:
        super().__init__()
        self.session_name = session_name

    def compose(self) -> ComposeResult:
        with Vertical(id="modal-box"):
            yield Label("Kill tmux session", id="modal-title")
            yield Label("─" * 40, id="modal-divider")
            yield Label(f"Kill [bold]{self.session_name}[/bold]?",
                        classes="modal-line")
            yield Label("[dim]This permanently ends the session.[/dim]",
                        classes="modal-line dim")
            yield Label("[dim]y confirm  ·  n / Esc cancel[/dim]",
                        id="modal-hint")

    def action_confirm(self) -> None:
        from rover.telemetry import _emit
        ok = kill_session(self.session_name)
        _emit({"event": "kill_session", "confirmed": True,
               "session": self.session_name})
        self.dismiss({"killed": ok})

    def action_cancel(self) -> None:
        from rover.telemetry import _emit
        _emit({"event": "kill_session", "confirmed": False,
               "session": self.session_name})
        self.dismiss({"killed": False, "cancelled": True})


class NewSessionInputModalScreen(ModalScreen):
    """Prompt for a tmux session name and create it."""

    BINDINGS = [
        Binding("escape", "cancel",  "Cancel", show=False),
        Binding("ctrl+c", "cancel",  "Cancel", show=False),
    ]

    DEFAULT_CSS = _MODAL_CSS

    def compose(self) -> ComposeResult:
        with Vertical(id="modal-box"):
            yield Label("New tmux session", id="modal-title")
            yield Label("─" * 40, id="modal-divider")
            yield Label("Session name (no spaces, no `:` or `.`):",
                        classes="modal-line dim")
            yield Input(placeholder="my-session", id="modal-input")
            yield Label("", id="modal-result", classes="modal-line")
            yield Label("[dim]Enter create  ·  Esc cancel[/dim]",
                        id="modal-hint")

    def on_mount(self) -> None:
        self.query_one("#modal-input", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        from rover.session_manager import new_session
        name = event.value.strip()
        if not name:
            self.dismiss({"created": False, "cancelled": True})
            return
        ok = new_session(name)
        result = self.query_one("#modal-result", Label)
        if ok:
            result.update(f"[green]✓[/green] created [bold]{name}[/bold]")
            self.set_timer(0.8, lambda: self.dismiss(
                {"created": True, "name": name}))
        else:
            result.update(f"[red]✗[/red] failed (collision?)")
            self.set_timer(1.4, lambda: self.dismiss(
                {"created": False, "name": name}))

    def action_cancel(self) -> None:
        self.dismiss({"created": False, "cancelled": True})


class ServerToggleModalScreen(ModalScreen):
    """Start/stop the dispatch server — confirm → work → result."""

    BINDINGS = [
        Binding("y",      "confirm", "Yes",    show=False),
        Binding("n",      "cancel",  "No",     show=False),
        Binding("escape", "cancel",  "Cancel", show=False),
    ]

    DEFAULT_CSS = _MODAL_CSS

    def __init__(self, config: dict) -> None:
        super().__init__()
        from rover import server_manager
        self.config = config
        self.port = int(config.get("dispatch_port", 4242))
        self.status = server_manager.server_status(port=self.port)
        self._phase = "confirm"   # confirm → running → result
        self._result_ok = False
        self._result_msg = ""

    def compose(self) -> ComposeResult:
        with Vertical(id="modal-box"):
            yield Label("Dispatch server", id="modal-title")
            yield Label("─" * 40, id="modal-divider")
            yield Label("", id="modal-msg", classes="modal-line")
            yield LoadingIndicator(id="modal-spinner")
            yield Label("", id="modal-hint")

    def on_mount(self) -> None:
        self.query_one("#modal-spinner", LoadingIndicator).display = False
        self._repaint()

    def _repaint(self) -> None:
        msg = self.query_one("#modal-msg", Label)
        hint = self.query_one("#modal-hint", Label)
        spinner = self.query_one("#modal-spinner", LoadingIndicator)

        if self._phase == "confirm":
            spinner.display = False
            if self.status["running"]:
                msg.update(
                    f"Stop dispatch server "
                    f"[dim](pid {self.status['pid']})[/dim]?"
                )
            else:
                msg.update(
                    f"Start dispatch server "
                    f"[dim](port {self.port})[/dim]?"
                )
            hint.update("[dim]y confirm  ·  n / Esc cancel[/dim]")

        elif self._phase == "running":
            spinner.display = True
            msg.update(
                "[dim]stopping...[/dim]" if self.status["running"]
                else "[dim]starting (up to 15s)...[/dim]"
            )
            hint.update("")

        elif self._phase == "result":
            spinner.display = False
            if self._result_ok:
                msg.update(f"[green]✓[/green] {self._result_msg}")
            else:
                msg.update(f"[red]✗[/red] {self._result_msg}")
            hint.update("[dim]press any key to close[/dim]")

    def action_confirm(self) -> None:
        if self._phase == "result":
            self.dismiss({"ok": self._result_ok})
            return
        if self._phase != "confirm":
            return
        self._phase = "running"
        self._repaint()
        self.run_worker(self._do_work, thread=True, exclusive=True)

    def action_cancel(self) -> None:
        if self._phase == "running":
            # Don't interrupt in-flight work; ignore Esc while spinning.
            return
        if self._phase == "result":
            self.dismiss({"ok": self._result_ok})
            return
        self.dismiss({"cancelled": True})

    def on_key(self, event) -> None:
        # In result phase, any key dismisses (consistent with old UX).
        if self._phase == "result":
            event.prevent_default()
            event.stop()
            self.dismiss({"ok": self._result_ok})

    def _do_work(self) -> None:
        from rover import server_manager
        if self.status["running"]:
            ok, msg = server_manager.stop_server(port=self.port)
        else:
            repo = server_manager.find_dispatch_repo(self.config)
            if repo is None:
                ok, msg = False, (
                    "Could not find the dispatch repo. "
                    "Set dispatch_repo_path in ~/.rover/config.json"
                )
            else:
                ok, msg = server_manager.start_server(repo, port=self.port)
        self.app.call_from_thread(self._on_done, ok, msg)

    def _on_done(self, ok: bool, msg: str) -> None:
        self._result_ok = ok
        self._result_msg = msg
        self._phase = "result"
        self._repaint()


# ---------------------------------------------------------------------------
# Main menu screen
# ---------------------------------------------------------------------------

class MainMenuScreen(Screen):
    """The primary rover menu: session list + action keys."""

    BINDINGS = [
        Binding("q",      "quit_menu",      "Quit",     show=False),
        Binding("ctrl+c", "quit_menu",      "Quit",     show=False),
        Binding("d",      "dispatch",       "Dispatch", show=False),
        Binding("s",      "settings",       "Settings", show=False),
        Binding("a",      "altergo",        "Altergo",  show=False),
        Binding("y",      "yolo",           "Yolo",     show=False),
        Binding("b",      "server_toggle",  "Server",   show=False),
        Binding("x",      "kill_session",   "Kill",     show=False),
        Binding("r",      "recall",         "Recall",   show=False),
        Binding("n",      "new_session",    "New tmux", show=False),
        Binding("c",      "caffeinate",     "Caff.",    show=False),
        Binding("enter",  "attach_current", "Attach",   show=False),
        Binding("up",     "cursor_up",      "Up",       show=False),
        Binding("k",      "cursor_up",      "Up",       show=False),
        Binding("down",   "cursor_down",    "Down",     show=False),
        Binding("j",      "cursor_down",    "Down",     show=False),
        Binding("1",      "digit(1)",       "",         show=False),
        Binding("2",      "digit(2)",       "",         show=False),
        Binding("3",      "digit(3)",       "",         show=False),
        Binding("4",      "digit(4)",       "",         show=False),
        Binding("5",      "digit(5)",       "",         show=False),
        Binding("6",      "digit(6)",       "",         show=False),
        Binding("7",      "digit(7)",       "",         show=False),
        Binding("8",      "digit(8)",       "",         show=False),
        Binding("9",      "digit(9)",       "",         show=False),
        Binding("0",      "digit(0)",       "",         show=False),
        # Keyboard scroll — mouse wheel is eaten by Termius's own scrollback,
        # so we bind physical keys. PageUp/PageDown + Home/End for desktop
        # SSH clients; `less_than_sign` / `greater_than_sign` (Shift+<comma>
        # and Shift+<period>) for mobile keyboards where PageUp/PageDown
        # aren't easily reachable.
        Binding("pageup",             "scroll_up_page",   "", show=False),
        Binding("pagedown",           "scroll_down_page", "", show=False),
        Binding("less_than_sign",     "scroll_up_page",   "", show=False),
        Binding("greater_than_sign",  "scroll_down_page", "", show=False),
        Binding("home",               "scroll_home",      "", show=False),
        Binding("end",                "scroll_end",       "", show=False),
    ]

    DEFAULT_CSS = """
    MainMenuScreen {
        background: #0d0d1a;
        align: center top;
        /* Screen can scroll when viewport is too short (keyboard open on
           mobile). Mouse wheel is eaten by Termius so we bind PageUp/PageDown
           + </> below for keyboard-driven scroll. Scrollbar kept thin and
           dim so it doesn't dominate. */
        overflow-y: auto;
        overflow-x: hidden;
        scrollbar-size-vertical: 1;
        scrollbar-background: #0d0d1a;
        scrollbar-background-hover: #0d0d1a;
        scrollbar-background-active: #0d0d1a;
        scrollbar-color: #1a1a2a;
        scrollbar-color-hover: #2a3a4a;
        scrollbar-color-active: #00d7ff;
    }

    #menu-figlet {
        width: 100%;
        content-align: center middle;
        text-align: center;
        padding: 0;
        color: #5fff87;
    }

    #menu-box {
        width: 100%;
        height: auto;
        border: solid #404060;
        padding: 0 1;
        margin: 0;
    }

    #menu-header {
        height: 1;
        layout: horizontal;
    }

    #menu-version {
        width: auto;
        color: #505070;
    }

    #menu-clock {
        width: 1fr;
        content-align: right middle;
        color: #505070;
    }

    #menu-caff {
        width: auto;
        color: yellow;
        padding-right: 1;
    }

    #menu-stats {
        height: auto;
        color: #606080;
        padding-bottom: 0;
    }

    #menu-divider-top {
        color: #404060;
        height: 1;
    }

    #sessions-header {
        text-style: bold;
        color: #c0c0e0;
        height: 1;
        padding: 0;
    }

    #sessions-empty {
        color: #505070;
        height: auto;
        padding: 0;
    }

    SessionsTable {
        height: auto;
        max-height: 10;
        border: none;
        padding: 0;
        margin: 0;
        background: #0d0d1a;
        scrollbar-size: 0 0;
    }

    SessionsTable > .datatable--header {
        display: none;
    }

    SessionsTable > .datatable--cursor {
        background: #1a2a3a;
        color: #ffffff;
    }

    #menu-divider-mid {
        color: #404060;
        height: 1;
        margin-top: 0;
    }

    #actions-label {
        text-style: bold dim;
        height: 1;
        padding: 0;
        color: #505070;
    }

    #actions-container {
        height: auto;
        padding: 0;
        margin: 0;
    }

    .action-row {
        height: 1;
        layout: horizontal;
    }

    .action-key {
        width: 4;
        color: #00d7ff;
        text-style: bold;
        padding-left: 2;
    }

    .action-label {
        width: 1fr;
        color: #606080;
    }

    .action-status {
        width: auto;
        color: #404040;
        padding-right: 1;
    }

    .action-status.online {
        color: green;
    }

    .action-status.awake {
        color: yellow;
    }

    #menu-number-hint {
        color: #00d7ff;
        height: 1;
        padding-top: 1;
        text-align: center;
    }

    #menu-hint {
        height: auto;
        dock: bottom;
        background: #0d0d1a;
        color: #606080;
    }
    """

    def __init__(
        self,
        config: dict,
        hours: float = 2.0,
    ) -> None:
        super().__init__()
        self.config = config
        self.hours = hours
        self._sessions: list[TmuxSession] = []
        self._stats: MenuStats | None = None
        self._number_buffer: str = ""

    # ── Composition ────────────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        header_font = self.config.get("header_font", "thin") or "thin"
        nickname = self.config.get("nickname", "").strip()
        show_nickname = bool(self.config.get("show_nickname_in_header", True))
        use_nickname = bool(nickname) and show_nickname
        try:
            sz = os.get_terminal_size()
            term_w, term_h = sz.columns, sz.lines
        except OSError:
            term_w, term_h = 80, 24
        # Keep the figlet at any reasonable size; only drop it on pathologically
        # short terminals where even the action rows wouldn't fit.
        if term_w >= 40 and term_h >= 14:
            figlet_text = nickname if use_nickname else "rover"
            yield Static(_figlet_renderable(header_font, figlet_text, term_w), id="menu-figlet")
        # Textual requires a Container/Vertical/Horizontal for nested widgets;
        # Static is leaf-only and silently overlaps children when used as a
        # container, which produced the broken-looking stacked render.
        with Vertical(id="menu-box"):
            with Horizontal(id="menu-header"):
                yield Label(f"rover v{__version__}", id="menu-version")
                yield Label("", id="menu-caff")
                yield Label(_now_str(), id="menu-clock")
            yield Static("", id="menu-stats")
            yield Static("─" * 60, id="menu-divider-top")
            yield Label("SESSIONS", id="sessions-header")
            yield Static("(no sessions)", id="sessions-empty")
            yield SessionsTable(id="sessions-table")
            yield Static("─" * 60, id="menu-divider-mid")
            yield Static("", id="actions-label")
            yield Static("", id="actions-container")
            yield Static("", id="menu-number-hint")
        yield Static("", id="menu-hint")

    def on_mount(self) -> None:
        self._refresh_data()
        self._update_clock()
        self.set_interval(5.0, self._on_timer)
        self.set_interval(1.0, self._update_clock)

    # ── Data refresh ─────────────────────────────────────────────────────────

    def _refresh_data(self) -> None:
        """Fetch sessions + stats and repaint."""
        self._sessions = list_sessions()

        # Clamp cursor to valid range
        tbl = self.query_one("#sessions-table", SessionsTable)
        if tbl.row_count > 0:
            cursor = tbl.cursor_row or 0
            max_row = len(self._sessions) - 1
            if cursor > max_row:
                tbl.move_cursor(row=max(0, max_row))

        # fetch stats in background so we don't block the event loop
        def _fetch():
            port = int(self.config.get("dispatch_port", 4242))
            stats = fetch_menu_stats(port=port, hours=1.0)
            self.call_from_thread(self._on_stats_fetched, stats)

        threading.Thread(target=_fetch, daemon=True).start()

        self._repaint_sessions()
        self._repaint_actions()
        self._repaint_hint()

    def _on_stats_fetched(self, stats: MenuStats) -> None:
        self._stats = stats
        self._repaint_stats()

    def _on_timer(self) -> None:
        self._refresh_data()

    def _update_clock(self) -> None:
        try:
            self.query_one("#menu-clock", Label).update(_now_str())
        except Exception:
            pass
        # caffeinate status glyph
        try:
            caff_lbl = self.query_one("#menu-caff", Label)
            if caffeinate.is_available() and caffeinate.is_awake():
                caff_lbl.update("\u2615 awake")
                caff_lbl.display = True
            else:
                caff_lbl.update("")
                caff_lbl.display = False
        except Exception:
            pass

    # ── Repaint helpers ───────────────────────────────────────────────────────

    def _repaint_stats(self) -> None:
        try:
            stats_widget = self.query_one("#menu-stats", Static)
        except Exception:
            return
        if self._stats is None:
            stats_widget.update("")
            return
        s = self._stats
        if not s.server_online:
            stats_widget.update("[dim]dispatch offline[/dim]")
            return
        tok = _fmt_tokens(s.total_tokens)
        cost = f"${s.total_cost_usd:.2f}"
        n = s.agent_count
        parts = [
            f"[dim]{n} agent{'s' if n != 1 else ''}[/dim]",
            f"[bold]{tok}[/bold][dim] tokens (1h)[/dim]",
            f"[dim]{cost}[/dim]",
        ]
        provider_parts = [
            f"{prov} {_fmt_tokens(t)}"
            for prov, t in sorted(s.tokens_by_provider.items(), key=lambda x: -x[1])
            if t > 0
        ][:3]
        line1 = "  \u00b7  ".join(parts)
        if provider_parts:
            line2 = "  \u00b7  ".join(provider_parts)
            stats_widget.update(f"{line1}\n{line2}")
        else:
            stats_widget.update(line1)

    def _repaint_sessions(self) -> None:
        try:
            tbl = self.query_one("#sessions-table", SessionsTable)
            empty = self.query_one("#sessions-empty", Static)
        except Exception:
            return

        tbl.clear()
        if not self._sessions:
            empty.display = True
            tbl.display = False
            empty.update(
                "(no tmux sessions running)\n"
                "[dim]Press [bold]n[/bold] to create one, or [bold]A[/bold] for altergo[/dim]"
            )
        else:
            empty.display = False
            tbl.display = True
            for idx, sess in enumerate(self._sessions):
                num = str(idx + 1)
                name = sess.name
                status = "[green]active[/green]" if sess.attached else "[dim]idle[/dim]"
                age = sess.age_str()
                tbl.add_row(num, name, status, age, key=str(idx))

    def _repaint_actions(self) -> None:
        try:
            container = self.query_one("#actions-container", Static)
        except Exception:
            return

        s = self._stats
        online = s is not None and s.server_online
        awake = caffeinate.is_available() and caffeinate.is_awake()

        if online:
            srv_label = "Stop dispatch server"
            srv_status = "[green]\u25cf online[/green]"
        else:
            srv_label = "Start dispatch server"
            srv_status = "[dim]\u25cb offline[/dim]"

        rows: list[tuple[str, str, str]] = [
            ("D", "Dispatch Dashboard", ""),
            ("A", "New altergo session", ""),
            ("Y", "Yolo session  [dim](skip confirm)[/dim]", ""),
            ("R", "Recall conversation  [dim](resume by picker)[/dim]", ""),
            ("B", srv_label, srv_status),
        ]
        if caffeinate.is_available():
            if awake:
                caff_label = "Sleep allowed"
                caff_status = "[yellow]\u2615 awake[/yellow]"
            else:
                caff_label = "Keep mac awake"
                caff_status = "[dim]\u25cb sleep ok[/dim]"
            rows.append(("C", caff_label, caff_status))

        rows += [
            ("S", "Settings", ""),
            ("Q", "Quit", ""),
        ]

        lines = []
        for key, label, status in rows:
            status_part = f"  {status}" if status else ""
            lines.append(
                f"  [bold #00d7ff]{key}[/bold #00d7ff]  [dim]{label}[/dim]{status_part}"
            )
        container.update("\n".join(lines))

    def _repaint_hint(self) -> None:
        try:
            hint = self.query_one("#menu-hint", Static)
        except Exception:
            return
        caff_hint = " \u00b7 C caffeinate" if caffeinate.is_available() else ""
        if self._number_buffer:
            hint.update(
                f"[dim]\u2191\u2193/jk navigate \u00b7 [/dim]"
                f"[bold #00d7ff]#{self._number_buffer}[/bold #00d7ff]"
                f"[dim] + Enter attach \u00b7 Y yolo \u00b7 A altergo \u00b7 D agents"
                f" \u00b7 B server{caff_hint} \u00b7 X kill \u00b7 S sets \u00b7 Q quit[/dim]"
            )
        else:
            hint.update(
                "[dim]\u2191\u2193/jk navigate \u00b7 Enter/num attach"
                " \u00b7 Y yolo \u00b7 A altergo \u00b7 D agents \u00b7 B server"
                f"{caff_hint} \u00b7 X kill \u00b7 S sets \u00b7 Q quit[/dim]"
            )

    # ── Key actions ───────────────────────────────────────────────────────────

    def action_quit_menu(self) -> None:
        self.app.exit(result={"action": "quit"})

    def action_dispatch(self) -> None:
        self.app.exit(result={"action": "dispatch"})

    def action_settings(self) -> None:
        self.app.exit(result={"action": "settings"})

    def action_altergo(self) -> None:
        self._number_buffer = ""
        self.app.exit(result={"action": "altergo"})

    def action_yolo(self) -> None:
        self._number_buffer = ""
        self.app.push_screen(YoloSubmenuScreen())

    def action_server_toggle(self) -> None:
        self._number_buffer = ""
        self.app.push_screen(
            ServerToggleModalScreen(self.config),
            callback=lambda _r: self._refresh_data(),
        )

    def action_kill_session(self) -> None:
        self._number_buffer = ""
        tbl = self.query_one("#sessions-table", SessionsTable)
        cursor = tbl.cursor_row
        if cursor is not None and 0 <= cursor < len(self._sessions):
            sess = self._sessions[cursor]
            self.app.push_screen(
                KillConfirmModalScreen(sess.name),
                callback=lambda _r: self._refresh_data(),
            )

    def action_recall(self) -> None:
        self._number_buffer = ""
        self.app.exit(result={"action": "altergo_recall"})

    def action_new_session(self) -> None:
        self._number_buffer = ""
        self.app.push_screen(
            NewSessionInputModalScreen(),
            callback=lambda _r: self._refresh_data(),
        )

    def action_caffeinate(self) -> None:
        if caffeinate.is_available():
            self._number_buffer = ""
            caffeinate.toggle()
            self._repaint_actions()
            self._update_clock()

    def action_attach_current(self) -> None:
        if self._number_buffer:
            try:
                idx = int(self._number_buffer) - 1
            except ValueError:
                idx = -1
            self._number_buffer = ""
            self._repaint_hint()
            if self._sessions and 0 <= idx < len(self._sessions):
                self.app.exit(result={"action": "attach", "session": self._sessions[idx].name})
            return

        tbl = self.query_one("#sessions-table", SessionsTable)
        cursor = tbl.cursor_row
        if cursor is not None and 0 <= cursor < len(self._sessions):
            self.app.exit(result={"action": "attach", "session": self._sessions[cursor].name})

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Intercept Enter inside the session table.

        The Screen-level `Binding("enter", "attach_current", ...)` never fires
        when focus is on the DataTable, because DataTable has its own `enter`
        binding that emits RowSelected. Routing that message back into
        action_attach_current makes Enter attach the cursor row (and keeps
        the number-buffer path — e.g. "3<Enter>" — working, since
        action_attach_current checks the buffer first).
        """
        event.stop()
        self.action_attach_current()

    def action_cursor_up(self) -> None:
        self._number_buffer = ""
        self.query_one("#sessions-table", SessionsTable).action_cursor_up()

    def action_cursor_down(self) -> None:
        self._number_buffer = ""
        self.query_one("#sessions-table", SessionsTable).action_cursor_down()

    # Screen-level scroll actions — bound to PageUp/PageDown/Home/End + `,`/`.`
    # so the user can scroll the whole menu when the mobile keyboard is open
    # and shrinks the viewport. Mouse wheel scrolling is unreliable over SSH
    # from Termius (client-side capture), hence the keyboard fallbacks.
    def action_scroll_up_page(self) -> None:
        self.scroll_page_up()

    def action_scroll_down_page(self) -> None:
        self.scroll_page_down()

    def action_scroll_home(self) -> None:
        self.scroll_home()

    def action_scroll_end(self) -> None:
        self.scroll_end()

    def action_digit(self, digit: int) -> None:
        total = len(self._sessions)
        self._number_buffer += str(digit)
        try:
            n = int(self._number_buffer)
        except ValueError:
            n = 0

        self._repaint_hint()

        if n == 0:
            # Leading zero — wait
            return

        if n > total:
            # Overshot — clear buffer
            self._number_buffer = ""
            self._repaint_hint()
            return

        if n * 10 > total:
            # No valid extension — commit immediately
            idx = n - 1
            self._number_buffer = ""
            self._repaint_hint()
            if self._sessions and 0 <= idx < len(self._sessions):
                self.app.exit(result={"action": "attach", "session": self._sessions[idx].name})
            return

        # Ambiguous (e.g. 30 sessions, pressed '2') — wait for another digit or Enter


# ---------------------------------------------------------------------------
# Custom DataTable subclass  (thin wrapper — no header, no border)
# ---------------------------------------------------------------------------

class SessionsTable(DataTable):
    """Slimmed-down DataTable for the session list."""

    def on_mount(self) -> None:
        self.show_header = False
        self.add_columns("#", "Name", "Status", "Age")
        self.cursor_type = "row"
        self.show_cursor = True


# ---------------------------------------------------------------------------
# Textual App
# ---------------------------------------------------------------------------

class MainMenuApp(App):
    """Textual wrapper around the main menu screen.

    Runs until the user triggers a navigation action, then exits with a
    result dict so the caller can handle side effects (attach, subprocess,
    etc.) outside Textual's event loop.
    """

    CSS = """
    Screen {
        background: #0d0d1a;
    }
    """

    def __init__(self, config: dict, hours: float = 2.0) -> None:
        super().__init__()
        self.config = config
        self.hours = hours

    def on_mount(self) -> None:
        self.push_screen(MainMenuScreen(self.config, self.hours))


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run_menu(config: dict, hours: float = 2.0) -> MenuAction:
    """Show the Textual session menu and handle user input.

    Returns a MenuAction when the user picks Dispatch / Settings / Quit.
    For attach, server-toggle, kill, etc., this function handles the side
    effect directly and re-enters the Textual app so the caller never sees
    those internal actions.

    The caller's while loop in __main__.py only needs to handle the three
    exported MenuAction values.
    """
    from rover.session_manager import attach_session, is_available

    if not is_available():
        from rich.console import Console
        Console().print("[bold red]tmux is not installed.[/bold red]")
        return MenuAction.QUIT

    while True:
        app = MainMenuApp(config=config, hours=hours)
        result: dict[str, Any] = app.run() or {}
        action = result.get("action", "quit")

        if action == "quit":
            return MenuAction.QUIT

        if action == "dispatch":
            return MenuAction.DISPATCH

        if action == "settings":
            return MenuAction.SETTINGS

        if action == "attach":
            sess_name = result.get("session", "")
            if sess_name:
                attach_session(sess_name)
            # attach_session blocks until the user detaches, then returns.
            # Fall through to re-enter the Textual menu.
            continue

        if action == "altergo":
            from rover.altergo_launcher import run_altergo_launcher
            from rover.config import save_config
            from rover.telemetry import _emit
            yolo = result.get("yolo", False)
            yolo_resume = result.get("yolo_resume", False)
            if yolo_resume:
                _emit({"event": "launch", "mode": "yolo_resume_last"})
            elif yolo:
                _emit({"event": "launch", "mode": "yolo"})
            run_altergo_launcher(config, save_config, yolo=yolo, yolo_resume=yolo_resume)
            continue

        if action == "yolo_pick":
            from rover.altergo_launcher import run_yolo_resume_pick
            from rover.config import save_config
            run_yolo_resume_pick(config, save_config)
            continue

        if action == "altergo_recall":
            import os
            os.execvp("altergo", ["altergo", "--recall"])
            continue  # unreachable; satisfies linter

        # Unknown action — just quit safely
        return MenuAction.QUIT
