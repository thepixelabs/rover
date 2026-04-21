"""Settings screen for rover.

Full-screen form for editing all user-facing config values.  Pressing
Save & return (or Ctrl+S) writes the config atomically via save_config()
and pops this screen.  Escape cancels without saving.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Button, Input, Label, Select, Static, Switch

from rover.config import load_config, save_config
from rover.banner import HEADER_FONTS, ANIMATION_PACKS

_THEME_OPTIONS = [
    ("Cyber (default)",  "cyber"),
    ("Sunset",           "sunset"),
    ("Ocean",            "ocean"),
    ("Mono",             "mono"),
    ("Forest",           "forest"),
    ("Lavender",         "lavender"),
    ("Rainbow",          "rainbow"),
]

_TIME_WINDOW_MIN = 1
_TIME_WINDOW_MAX = 24
_REFRESH_MIN     = 5
_REFRESH_MAX     = 300


class SettingsScreen(Screen):
    """Full-screen settings form."""

    BINDINGS = [
        Binding("escape", "cancel",  "Cancel"),
        Binding("ctrl+s", "save",    "Save & return"),
    ]

    DEFAULT_CSS = """
    SettingsScreen {
        align: center middle;
        overflow-y: auto;
    }

    #settings-container {
        width: 90%;
        min-width: 30;
        max-width: 74;
        height: auto;
        overflow-x: hidden;
        border: tall $primary;
        padding: 1 2;
    }

    #settings-title {
        text-style: bold;
        color: $accent;
        margin-bottom: 0;
        content-align: center middle;
    }

    #settings-divider {
        color: $primary-darken-2;
        margin-bottom: 1;
    }

    /* ── Error strip ─────────────────────────────────────────────────────── */

    #error-msg {
        color: $background;
        background: $error;
        height: auto;
        padding: 0 1;
        margin-bottom: 1;
        display: none;
    }

    #error-msg.visible {
        display: block;
    }

    /* ── Section dividers ────────────────────────────────────────────────── */

    .section-rule {
        color: $accent;
        margin-top: 1;
        margin-bottom: 0;
    }

    /* ── Stacked field rows (label above input — works at any width) ──────── */

    .field-row {
        height: auto;
        margin-bottom: 1;
    }

    .field-label {
        color: $text-muted;
        text-style: dim;
        width: 100%;
        margin-bottom: 0;
    }

    .field-input {
        width: 1fr;
        max-width: 50;
    }

    .field-input-wide {
        width: 1fr;
        max-width: 50;
    }

    .field-unit {
        color: $text-muted;
        padding-left: 1;
        width: auto;
    }

    /* ── Switch row keeps inline layout (Switch widget is compact) ────────── */

    .switch-row {
        height: auto;
        margin-bottom: 0;
        layout: horizontal;
        align: left middle;
    }

    .switch-label {
        color: $text-muted;
        text-style: dim;
        width: auto;
        margin-right: 2;
        content-align: left middle;
    }

    /* ── Small help caption under inputs / switches ──────────────────────── */

    .field-caption {
        color: $text-muted;
        text-style: dim;
        height: auto;
        margin-bottom: 1;
        padding-left: 1;
    }

    /* ── Input+unit inline pair ──────────────────────────────────────────── */

    .input-unit-row {
        height: auto;
        layout: horizontal;
        align: left middle;
    }

    /* ── Buttons footer ─────────────────────────────────────────────────── */

    #button-row {
        height: auto;
        layout: horizontal;
        margin-top: 2;
        align: left middle;
    }

    #save-btn {
        width: 2fr;
        margin-right: 1;
    }

    #cancel-btn {
        width: 1fr;
    }

    /* ── Keyboard hint bar (docked to screen bottom) ─────────────────────── */

    #kbd-hint {
        dock: bottom;
        height: 1;
        color: $text-muted;
        text-style: dim;
        content-align: center middle;
        background: $surface;
    }
    """

    def compose(self) -> ComposeResult:
        with Vertical(id="settings-container"):
            yield Static("SETTINGS", id="settings-title")
            yield Static("─" * 40, id="settings-divider")

            # Error strip — hidden by default, shown via _show_error()
            yield Static("", id="error-msg")

            # ── GENERAL ───────────────────────────────────────────────────────
            yield Static("── GENERAL ──────────────────────────────", classes="section-rule")

            with Vertical(classes="field-row"):
                yield Label("Nickname", classes="field-label")
                yield Input(
                    placeholder="leave empty to use system username",
                    id="input-nickname",
                    classes="field-input",
                )
                yield Label(
                    "Used in greetings and tmux session names.",
                    classes="field-caption",
                )

            with Vertical(classes="field-row"):
                yield Label("Theme", classes="field-label")
                yield Select(
                    options=_THEME_OPTIONS,
                    id="select-theme",
                    classes="field-input",
                )

            with Vertical(classes="field-row"):
                with Vertical(classes="switch-row"):
                    yield Label(
                        "Show nickname in header",
                        classes="switch-label",
                    )
                    yield Switch(id="switch-show-nickname")
                yield Label(
                    "On: the big banner spells your nickname. "
                    "Off: it always spells \"rover\".",
                    classes="field-caption",
                )

            # ── APPEARANCE ────────────────────────────────────────────────────
            yield Static("── APPEARANCE ───────────────────────────", classes="section-rule")

            with Vertical(classes="field-row"):
                yield Label("Header font", classes="field-label")
                yield Select(
                    options=HEADER_FONTS,
                    id="select-header-font",
                    classes="field-input",
                )

            with Vertical(classes="field-row"):
                yield Label("Animation pack", classes="field-label")
                yield Select(
                    options=ANIMATION_PACKS,
                    id="select-animation-pack",
                    classes="field-input",
                )

            # ── DISPATCH ──────────────────────────────────────────────────────
            yield Static("── DISPATCH ─────────────────────────────", classes="section-rule")

            with Vertical(classes="field-row"):
                yield Label("Time window", classes="field-label")
                with Vertical(classes="input-unit-row"):
                    yield Input(
                        id="input-time-window",
                        classes="field-input",
                    )
                    yield Static("hours", classes="field-unit")
                yield Label(
                    f"How far back the agent dashboard looks for activity "
                    f"({_TIME_WINDOW_MIN}\u2013{_TIME_WINDOW_MAX} hours).",
                    classes="field-caption",
                )

            with Vertical(classes="field-row"):
                yield Label("Refresh interval", classes="field-label")
                with Vertical(classes="input-unit-row"):
                    yield Input(
                        id="input-refresh",
                        classes="field-input",
                    )
                    yield Static("seconds", classes="field-unit")
                yield Label(
                    f"How often the main menu re-fetches dispatch stats "
                    f"({_REFRESH_MIN}\u2013{_REFRESH_MAX} seconds).",
                    classes="field-caption",
                )

            # ── ALTERGO ───────────────────────────────────────────────────────
            yield Static("── ALTERGO ──────────────────────────────", classes="section-rule")

            with Vertical(classes="field-row"):
                yield Label("Git workspace", classes="field-label")
                yield Input(
                    placeholder="~/Documents/git",
                    id="input-git-workspace",
                    classes="field-input-wide",
                )
                yield Label(
                    "Parent folder containing your git projects. "
                    "Altergo and yolo flows scan this for repos.",
                    classes="field-caption",
                )

            # ── Actions ───────────────────────────────────────────────────────
            with Horizontal(id="button-row"):
                yield Button("Save & return", variant="primary", id="save-btn")
                yield Button("Cancel", variant="default", id="cancel-btn")

        # Keyboard hint docked to the screen bottom (outside the container)
        yield Static("[Esc] cancel   [Ctrl+S] save", id="kbd-hint")

    def on_mount(self) -> None:
        cfg = load_config()

        self.query_one("#input-nickname", Input).value = cfg.get("nickname", "")
        self.query_one("#input-time-window", Input).value = str(
            cfg.get("time_window_hours", 2)
        )
        self.query_one("#input-refresh", Input).value = str(
            cfg.get("refresh_seconds", 30)
        )
        self.query_one("#input-git-workspace", Input).value = cfg.get(
            "git_workspace", ""
        )

        theme_value = cfg.get("theme", "cyber")
        self.query_one("#select-theme", Select).value = theme_value

        header_font = cfg.get("header_font", "smslant")
        self.query_one("#select-header-font", Select).value = header_font

        anim_pack = cfg.get("animation_pack", "dots")
        self.query_one("#select-animation-pack", Select).value = anim_pack

        self.query_one("#switch-show-nickname", Switch).value = bool(
            cfg.get("show_nickname_in_header", True)
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "save-btn":
            self.action_save()
        elif event.button.id == "cancel-btn":
            self.action_cancel()

    def _show_error(self, msg: str) -> None:
        error_widget = self.query_one("#error-msg", Static)
        error_widget.update(f"  \u2717  {msg}")
        error_widget.add_class("visible")

    def _clear_error(self) -> None:
        error_widget = self.query_one("#error-msg", Static)
        error_widget.update("")
        error_widget.remove_class("visible")

    def action_save(self) -> None:
        """Validate inputs, write config, and pop screen."""
        import pathlib
        self._clear_error()

        nickname = self.query_one("#input-nickname", Input).value.strip()

        raw_time_window = self.query_one("#input-time-window", Input).value.strip()
        try:
            time_window = int(raw_time_window)
        except ValueError:
            self._show_error("Time window must be a whole number.")
            return
        if not (_TIME_WINDOW_MIN <= time_window <= _TIME_WINDOW_MAX):
            self._show_error(
                f"Time window must be between {_TIME_WINDOW_MIN} and "
                f"{_TIME_WINDOW_MAX} hours."
            )
            return

        raw_refresh = self.query_one("#input-refresh", Input).value.strip()
        try:
            refresh_seconds = int(raw_refresh)
        except ValueError:
            self._show_error("Refresh interval must be a whole number.")
            return
        if not (_REFRESH_MIN <= refresh_seconds <= _REFRESH_MAX):
            self._show_error(
                f"Refresh interval must be between {_REFRESH_MIN} and "
                f"{_REFRESH_MAX} seconds."
            )
            return

        # Validate git workspace (empty is fine — means "ask me on first use")
        git_workspace_raw = self.query_one("#input-git-workspace", Input).value.strip()
        git_workspace = ""
        if git_workspace_raw:
            resolved = pathlib.Path(git_workspace_raw).expanduser().resolve()
            if not resolved.is_dir():
                self._show_error(
                    f"Git workspace not found: {git_workspace_raw}"
                )
                return
            git_workspace = str(resolved)

        # Guard against Select.BLANK (no selection) — fall back to defaults.
        _theme_raw = self.query_one("#select-theme", Select).value
        theme = str(_theme_raw) if _theme_raw is not Select.BLANK else "cyber"

        _font_raw = self.query_one("#select-header-font", Select).value
        header_font = str(_font_raw) if _font_raw is not Select.BLANK else "smslant"

        _anim_raw = self.query_one("#select-animation-pack", Select).value
        animation_pack = str(_anim_raw) if _anim_raw is not Select.BLANK else "dots"
        show_nickname_in_header = self.query_one(
            "#switch-show-nickname", Switch
        ).value

        # Merge over the currently saved config so we preserve any keys we
        # don't own (e.g. dispatch_port set by another path).
        cfg = load_config()

        cfg["nickname"]           = nickname
        cfg["time_window_hours"]  = time_window
        cfg["refresh_seconds"]    = refresh_seconds
        cfg["theme"]              = theme
        cfg["header_font"]        = header_font
        cfg["animation_pack"]          = animation_pack
        cfg["show_nickname_in_header"] = show_nickname_in_header
        cfg["git_workspace"]           = git_workspace

        save_config(cfg)

        self._close()

    def action_cancel(self) -> None:
        """Pop screen without saving."""
        self._close()

    def _close(self) -> None:
        """Return from Settings.

        When Settings was launched directly from the rover main menu
        (``_start_on_settings=True``), it is the only pushed screen on top of
        Textual's empty default screen — popping would leave the user staring
        at a blank Textual screen until they pressed ``q`` to exit the app.
        In that case, exit the Textual app entirely so rover's main menu
        re-renders immediately.

        When Settings was opened from within the Textual dashboard (via the
        app-level ``s`` binding), there is a Dashboard screen to return to, so
        we pop the screen as normal.
        """
        if getattr(self.app, "_start_on_settings", False):
            self.app.exit()
        else:
            self.app.pop_screen()
