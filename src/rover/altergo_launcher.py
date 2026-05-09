"""Altergo session launcher sub-flow for rover.

Renders Textual-based picker screens for:
  - Git workspace configuration (first-time setup prompt)
  - Project selection  (subdirs with .git in the workspace)
  - Account selection  (always shown; displays each account's provider)
  - Yolo resume pick  (cross-account session picker)

Public entry points
-------------------
run_altergo_launcher(config, save_config_fn)
  Returns normally if the user cancels at any step, and also returns after
  altergo exits (rover launches altergo as a child process via
  subprocess.run so the user lands back in the rover menu on exit).

run_yolo_resume_pick(config, save_config_fn)
  Cross-account session picker that execs altergo with --yolo-resume=<UUID>.
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import string
import subprocess
from rich.console import Console

# ── Layout constants ─────────────────────────────────────────────────────────

_DIM_BORDER    = "#404060"
_CYAN          = "#00d7ff"

_LETTERS   = string.ascii_lowercase
_PAGE_SIZE = 26

_KNOWN_PROVIDERS = ("claude", "gemini", "codex", "copilot")

# Sentinel return values from the project picker — matched on exact string
# equality after _run_picker returns. Never collide with real project names
# because real names can't contain "::" (dirnames are sanitized upstream).
_PROJECT_NEW        = "::new-project::"
_PROJECT_WORKSPACE  = "::workspace-root::"

# Sentinel returned by _run_picker when the user pressed q / Backspace and
# the picker was launched with back_enabled=True. Callers loop back to the
# previous step in the multi-step project → account → provider flow instead
# of exiting entirely (which is what None means).
_PICKER_BACK        = "::back::"


# ── Path helpers ─────────────────────────────────────────────────────────────

def _real_home() -> pathlib.Path:
    """Real user home, ignoring altergo's HOME swap.

    altergo overrides HOME to ``~/.altergo/accounts/<name>/`` for each
    managed session. Rover must resolve paths relative to the *real* user
    home (from the passwd database) so that ``_ALTERGO_DIR`` / ``_ACCOUNTS_DIR``
    are always correct regardless of whether rover is launched from inside one
    of those managed sessions.
    """
    try:
        import pwd
        return pathlib.Path(pwd.getpwuid(os.getuid()).pw_dir)
    except Exception:
        return pathlib.Path.home()


# Computed after _real_home() is defined so that altergo's HOME override
# (which sets HOME to ~/.altergo/accounts/<name>/) does not corrupt these
# module-level paths. pathlib.Path.home() reads $HOME; _real_home() reads
# the passwd database entry, which is immune to the env-var swap.
_ALTERGO_DIR   = _real_home() / ".altergo"
_ACCOUNTS_DIR  = _ALTERGO_DIR / "accounts"


# ── Discovery helpers ─────────────────────────────────────────────────────────

def _get_account_provider(account_name: str) -> str:
    """Return the provider string for an account (defaults to 'claude')."""
    account_home = _ACCOUNTS_DIR / account_name
    meta_file = account_home / "account.json"
    if meta_file.exists():
        try:
            with meta_file.open("r", encoding="utf-8") as fh:
                data = json.load(fh)
            provider = data.get("provider", "")
            if provider in _KNOWN_PROVIDERS:
                return provider
        except Exception:
            pass
    if (account_home / ".claude").is_dir():
        return "claude"
    return "claude"


def _list_git_projects_with_mtime(workspace: str) -> list[tuple[str, float]]:
    """Return (name, mtime) tuples for git subdirectories in workspace."""
    ws = pathlib.Path(workspace).expanduser().resolve()
    if not ws.is_dir():
        return []
    result = []
    for entry in ws.iterdir():
        if entry.is_dir() and (entry / ".git").exists():
            try:
                mtime = entry.stat().st_mtime
            except OSError:
                mtime = 0.0
            result.append((entry.name, mtime))
    return result


def list_git_projects(workspace: str) -> list[str]:
    """Return sorted names of subdirectories containing a .git folder."""
    return sorted(name for name, _ in _list_git_projects_with_mtime(workspace))


def _list_accounts_with_mtime() -> list[tuple[str, float]]:
    """Return (name, mtime) tuples for altergo accounts."""
    if not _ACCOUNTS_DIR.is_dir():
        return []
    result = []
    for entry in _ACCOUNTS_DIR.iterdir():
        if entry.is_dir() and not entry.name.startswith("."):
            try:
                mtime = entry.stat().st_mtime
            except OSError:
                mtime = 0.0
            result.append((entry.name, mtime))
    return result


def list_altergo_accounts() -> list[str]:
    """Return sorted altergo account names from ~/.altergo/accounts/."""
    return sorted(name for name, _ in _list_accounts_with_mtime())


# ── tmux session helpers ──────────────────────────────────────────────────────

_TMUX_UNSAFE_RE = re.compile(r"[^A-Za-z0-9_\-/]")


def _sanitize_tmux_segment(raw: str) -> str:
    """Return a tmux-safe version of a name segment."""
    if not raw:
        return "unknown"
    cleaned = _TMUX_UNSAFE_RE.sub("-", raw).strip("-")
    return cleaned or "unknown"


def _derive_session_name(
    project_path: pathlib.Path | None,
    account: str,
    provider: str,
) -> str:
    """Build the tmux session name ``<project>/<account>/<provider>``."""
    if project_path is not None and project_path.name:
        project_seg = project_path.name
    else:
        project_seg = pathlib.Path.cwd().name or "project"

    return (
        f"{_sanitize_tmux_segment(project_seg)}/"
        f"{_sanitize_tmux_segment(account)}/"
        f"{_sanitize_tmux_segment(provider)}"
    )


# ── Textual picker screen ─────────────────────────────────────────────────────

def _run_picker(
    title: str,
    items: list[str],
    subtitle: str = "",
    display_items: list[str] | None = None,
    sort_keys: list[float] | None = None,
    pin_top_count: int = 0,
    back_enabled: bool = False,
) -> str | None:
    """Show a letter-keyed paginated Textual picker. Returns selected item or None.

    ``pin_top_count`` keeps the first N items of ``items`` pinned at the top of
    the list regardless of sort order — used for action sentinels like
    "create new project" that should always be reachable on page 1.

    ``back_enabled`` turns ``q`` and ``Backspace`` into a "back one step"
    action that returns the ``_PICKER_BACK`` sentinel. ``Esc`` still exits
    the whole flow (returns None). When False (the default), ``q`` and
    ``Backspace`` also exit entirely — there's no previous step to return to.
    """
    from textual.app import App, ComposeResult
    from textual.binding import Binding
    from textual.containers import Vertical
    from textual.screen import Screen
    from textual.widgets import DataTable, Label

    if not items:
        return None

    display = display_items if display_items is not None else items

    class PickerScreen(Screen):
        BINDINGS = [
            # Esc + Ctrl+C always exit the whole multi-step flow (return None).
            # Backspace routes through `action_back`: when back_enabled is
            # True the picker exits with _PICKER_BACK so the caller re-runs
            # the previous step; when False it behaves like cancel.
            #
            # `q` is deliberately NOT bound here — it's one of the a-z
            # pick-letter slots (items 17 on a 26-item page are keyed `q`).
            # Binding it to back as well would shadow the letter-pick and
            # make the 17th item unselectable.
            Binding("escape",    "cancel", "Cancel", show=False),
            Binding("ctrl+c",    "cancel", "Cancel", show=False),
            Binding("backspace", "back",   "Back",   show=False),
            Binding("]",         "next_page", "Next", show=False),
            Binding("[",         "prev_page", "Prev", show=False),
            Binding("right",     "next_page", "Next", show=False),
            Binding("left",      "prev_page", "Prev", show=False),
            # Tab is the discoverable mobile-keyboard paging key; priority=True
            # so Textual's default focus-cycling binding doesn't win first.
            Binding("tab",       "next_page", "Next", show=False, priority=True),
            Binding("shift+tab", "prev_page", "Prev", show=False, priority=True),
        ] + [
            Binding(ch, f"pick_letter('{ch}')", "", show=False)
            for ch in _LETTERS
            # 's' is reserved for toggle_sort when sort_keys are provided;
            # skip it here so there is no duplicate binding for that key.
            if not (ch == "s" and sort_keys is not None)
        ] + [
            Binding(ch.upper(), f"pick_letter('{ch}')", "", show=False)
            for ch in _LETTERS
        ] + (
            [Binding("s", "toggle_sort", "Sort", show=False)]
            if sort_keys is not None else []
        )

        DEFAULT_CSS = """
        PickerScreen {
            align: center middle;
            background: #0d0d1a;
            overflow-y: auto;
        }

        #picker-box {
            width: 90%;
            min-width: 30;
            max-width: 90;
            height: auto;
            overflow-x: hidden;
            border: solid #404060;
            padding: 0 1;
            background: #0d0d1a;
        }

        #picker-title {
            color: #00d7ff;
            text-style: bold;
            height: 1;
            padding-top: 1;
        }

        #picker-subtitle {
            color: #505070;
            height: 1;
        }

        #picker-divider {
            color: #404060;
            height: 1;
        }

        PickerTable {
            height: auto;
            min-height: 5;
            max-height: 28;
            border: none;
            margin: 0;
            padding: 0;
            background: #0d0d1a;
        }

        PickerTable > .datatable--header {
            display: none;
        }

        PickerTable > .datatable--cursor {
            background: #1a2040;
            color: #ffffff;
        }

        #picker-hint {
            color: #6060a0;
            height: auto;
            padding-bottom: 1;
        }
        """

        def __init__(self) -> None:
            super().__init__()
            self._page = 0
            self._sort = "name"

        def _sorted_indices(self) -> list[int]:
            pinned = list(range(min(pin_top_count, len(items))))
            rest = list(range(pin_top_count, len(items)))
            if self._sort == "modified" and sort_keys is not None:
                rest.sort(key=lambda i: -(sort_keys[i] or 0.0))
            else:
                rest.sort(key=lambda i: items[i].lower())
            return pinned + rest

        def _total_pages(self) -> int:
            return max(1, (len(items) + _PAGE_SIZE - 1) // _PAGE_SIZE)

        def compose(self) -> ComposeResult:
            with Vertical(id="picker-box"):
                yield Label(title, id="picker-title")
                if sort_keys is not None:
                    yield Label(
                        f"{subtitle}  \u00b7  sort: {self._sort}" if subtitle
                        else f"sort: {self._sort}",
                        id="picker-subtitle",
                    )
                elif subtitle:
                    yield Label(subtitle, id="picker-subtitle")
                else:
                    yield Label("", id="picker-subtitle")
                yield Label("\u2500" * 55, id="picker-divider")
                yield PickerTable(id="picker-table")
                yield Label("", id="picker-hint")

        def on_mount(self) -> None:
            self._repaint()
            self.query_one("#picker-table", PickerTable).focus()

        def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
            try:
                local_idx = int(event.row_key.value)
            except (TypeError, ValueError):
                return
            sorted_idx = self._sorted_indices()
            page_slice = sorted_idx[
                self._page * _PAGE_SIZE: (self._page + 1) * _PAGE_SIZE
            ]
            if 0 <= local_idx < len(page_slice):
                self.app.exit(result=items[page_slice[local_idx]])

        def _repaint(self) -> None:
            sorted_idx = self._sorted_indices()
            total = self._total_pages()
            self._page = min(self._page, total - 1)
            page_slice = sorted_idx[
                self._page * _PAGE_SIZE: (self._page + 1) * _PAGE_SIZE
            ]

            # Update subtitle (sort indicator)
            try:
                sub = self.query_one("#picker-subtitle", Label)
                if sort_keys is not None:
                    sort_label = "name" if self._sort == "name" else "modified"
                    full_sub = (
                        f"{subtitle}  \u00b7  sort: {sort_label}"
                        if subtitle else f"sort: {sort_label}"
                    )
                    sub.update(full_sub)
            except Exception:
                pass

            # Repaint table
            try:
                tbl = self.query_one("#picker-table", PickerTable)
                tbl.clear()
                for local_i, global_i in enumerate(page_slice):
                    letter = _LETTERS[local_i]
                    label = display[global_i]
                    tbl.add_row(letter, label, key=str(local_i))
            except Exception:
                pass

            # Hint bar
            try:
                hint_parts = ["  ↑↓/Enter select  ·  a–z jump"]
                if total > 1:
                    hint_parts.append(
                        f"  \u00b7  Tab/] next  \u00b7  Shift+Tab/[ prev"
                        f"  \u00b7  page {self._page + 1}/{total}"
                    )
                if sort_keys is not None:
                    hint_parts.append("  \u00b7  s sort")
                if back_enabled:
                    hint_parts.append("  \u00b7  Backspace back  \u00b7  Esc cancel")
                else:
                    hint_parts.append("  \u00b7  Esc cancel")
                self.query_one("#picker-hint", Label).update(
                    "[dim]" + "".join(hint_parts) + "[/dim]"
                )
            except Exception:
                pass

        def action_cancel(self) -> None:
            self.app.exit(result=None)

        def action_back(self) -> None:
            # q / Backspace: step back one level in a multi-step flow when
            # back_enabled, otherwise behave like cancel (matches what the
            # top-level picker expects — no previous step to return to).
            if back_enabled:
                self.app.exit(result=_PICKER_BACK)
            else:
                self.app.exit(result=None)

        def action_next_page(self) -> None:
            total = self._total_pages()
            if self._page < total - 1:
                self._page += 1
            self._repaint()

        def action_prev_page(self) -> None:
            if self._page > 0:
                self._page -= 1
            self._repaint()

        def action_toggle_sort(self) -> None:
            if sort_keys is not None:
                self._sort = "modified" if self._sort == "name" else "name"
                self._page = 0
                self._repaint()

        def action_pick_letter(self, letter: str) -> None:
            sorted_idx = self._sorted_indices()
            page_slice = sorted_idx[
                self._page * _PAGE_SIZE: (self._page + 1) * _PAGE_SIZE
            ]
            lkey = letter.lower()
            local_idx = _LETTERS.index(lkey) if lkey in _LETTERS else -1
            if local_idx < 0 or local_idx >= len(page_slice):
                return
            self.app.exit(result=items[page_slice[local_idx]])

    class PickerTable(DataTable):
        def on_mount(self) -> None:
            self.show_header = False
            self.add_columns("Key", "Label")
            self.cursor_type = "row"
            self.show_cursor = True

    class PickerApp(App):
        CSS = """
        Screen {
            background: #0d0d1a;
        }
        """

        def on_mount(self) -> None:
            self.push_screen(PickerScreen())

    app = PickerApp()
    return app.run()


# ── Workspace prompt screen ────────────────────────────────────────────────────

def _run_workspace_prompt() -> str | None:
    """Show a Textual workspace-path prompt. Returns resolved path or None."""
    from textual.app import App, ComposeResult
    from textual.binding import Binding
    from textual.containers import Vertical
    from textual.screen import Screen
    from textual.widgets import Button, Input, Label

    class WorkspaceScreen(Screen):
        BINDINGS = [
            Binding("escape",  "cancel", "Cancel",  show=False),
            Binding("ctrl+c",  "cancel", "Cancel",  show=False),
        ]

        DEFAULT_CSS = """
        WorkspaceScreen {
            align: center middle;
            background: #0d0d1a;
        }

        #ws-box {
            width: 90%;
            min-width: 30;
            max-width: 70;
            height: auto;
            overflow-x: hidden;
            border: solid #404060;
            padding: 1 2;
            background: #0d0d1a;
        }

        #ws-title {
            color: #00d7ff;
            text-style: bold;
            margin-bottom: 1;
        }

        #ws-divider {
            color: #404060;
            margin-bottom: 1;
        }

        .ws-hint {
            color: #505070;
            height: 1;
        }

        #ws-input {
            margin-top: 1;
            margin-bottom: 1;
            width: 100%;
        }

        #ws-error {
            color: red;
            height: 1;
            display: none;
        }

        #ws-error.visible {
            display: block;
        }

        #ws-btn {
            margin-top: 1;
        }
        """

        def compose(self) -> ComposeResult:
            with Vertical(id="ws-box"):
                yield Label("rover  \u00b7  workspace setup", id="ws-title")
                yield Label("\u2500" * 55, id="ws-divider")
                yield Label("Enter the path to your git workspace folder.", classes="ws-hint")
                yield Label("rover will scan it for repos each time you use this flow.", classes="ws-hint")
                yield Label("", classes="ws-hint")
                yield Label("Examples:  ~/Documents/git   ~/projects   ~/code", classes="ws-hint")
                yield Input(placeholder="~/Documents/git", id="ws-input")
                yield Label("", id="ws-error")
                yield Button("Confirm", variant="primary", id="ws-confirm")

        def on_mount(self) -> None:
            self.query_one("#ws-input", Input).focus()

        def _validate_and_submit(self) -> None:
            raw = self.query_one("#ws-input", Input).value.strip()
            if not raw:
                return
            resolved = pathlib.Path(raw).expanduser().resolve()
            if resolved.is_dir():
                self.app.exit(result=str(resolved))
            else:
                err = self.query_one("#ws-error", Label)
                err.update(f"\u2717 Not a directory: {resolved}")
                err.add_class("visible")

        def on_input_submitted(self, _event: Input.Submitted) -> None:
            self._validate_and_submit()

        def on_button_pressed(self, event: Button.Pressed) -> None:
            if event.button.id == "ws-confirm":
                self._validate_and_submit()

        def action_cancel(self) -> None:
            self.app.exit(result=None)

    class WorkspaceApp(App):
        CSS = "Screen { background: #0d0d1a; }"

        def on_mount(self) -> None:
            self.push_screen(WorkspaceScreen())

    return WorkspaceApp().run()


# ── New-project prompt ────────────────────────────────────────────────────────

def _run_new_project_prompt(workspace: str) -> pathlib.Path | None:
    """Prompt for a new project dir name under ``workspace``, create it, return the path.

    Creates ``workspace/<name>/`` with ``mkdir -p`` semantics and runs
    ``git init`` inside it so the repo shows up in future project-pick scans
    (``_list_git_projects_with_mtime`` filters for ``.git`` presence).
    Returns None on cancel / invalid name.
    """
    from textual.app import App, ComposeResult
    from textual.binding import Binding
    from textual.containers import Vertical
    from textual.screen import Screen
    from textual.widgets import Button, Input, Label

    class NewProjectScreen(Screen):
        BINDINGS = [
            Binding("escape", "cancel", "Cancel", show=False),
            Binding("ctrl+c", "cancel", "Cancel", show=False),
        ]

        DEFAULT_CSS = """
        NewProjectScreen {
            align: center middle;
            background: #0d0d1a;
        }

        #np-box {
            width: 90%;
            min-width: 30;
            max-width: 70;
            height: auto;
            overflow-x: hidden;
            border: solid #404060;
            padding: 1 2;
            background: #0d0d1a;
        }

        #np-title {
            color: #00d7ff;
            text-style: bold;
            margin-bottom: 1;
        }

        #np-divider {
            color: #404060;
            margin-bottom: 1;
        }

        .np-hint {
            color: #505070;
            height: 1;
        }

        #np-input {
            margin-top: 1;
            margin-bottom: 1;
            width: 100%;
        }

        #np-error {
            color: red;
            height: 1;
            display: none;
        }

        #np-error.visible {
            display: block;
        }

        #np-btn {
            margin-top: 1;
        }
        """

        def compose(self) -> ComposeResult:
            with Vertical(id="np-box"):
                yield Label("rover  \u00b7  new project", id="np-title")
                yield Label("\u2500" * 55, id="np-divider")
                yield Label("Create a new project folder under:", classes="np-hint")
                yield Label(f"  [dim]{workspace}[/dim]", classes="np-hint")
                yield Label("", classes="np-hint")
                yield Label("No spaces or slashes. `git init` runs automatically.",
                            classes="np-hint")
                yield Input(placeholder="my-new-project", id="np-input")
                yield Label("", id="np-error")
                yield Button("Create", variant="primary", id="np-confirm")

        def on_mount(self) -> None:
            self.query_one("#np-input", Input).focus()

        def _validate_and_submit(self) -> None:
            raw = self.query_one("#np-input", Input).value.strip()
            err = self.query_one("#np-error", Label)
            if not raw:
                return
            # Reject path traversal + anything tmux/fs-unfriendly. Matches
            # the sanitization applied to session-name segments elsewhere.
            if any(ch in raw for ch in "/\\ \t:.") or raw.startswith("-"):
                err.update("\u2717 Name can't contain spaces, slashes, colons, or dots.")
                err.add_class("visible")
                return
            target = pathlib.Path(workspace).expanduser() / raw
            if target.exists():
                err.update(f"\u2717 Already exists: {target.name}")
                err.add_class("visible")
                return
            try:
                target.mkdir(parents=True, exist_ok=False)
                subprocess.run(
                    ["git", "init", "-q"],
                    cwd=str(target),
                    check=False,
                    timeout=5,
                )
            except (OSError, subprocess.SubprocessError) as exc:
                err.update(f"\u2717 {exc}")
                err.add_class("visible")
                return
            self.app.exit(result=str(target))

        def on_input_submitted(self, _event: Input.Submitted) -> None:
            self._validate_and_submit()

        def on_button_pressed(self, event: Button.Pressed) -> None:
            if event.button.id == "np-confirm":
                self._validate_and_submit()

        def action_cancel(self) -> None:
            self.app.exit(result=None)

    class NewProjectApp(App):
        CSS = "Screen { background: #0d0d1a; }"

        def on_mount(self) -> None:
            self.push_screen(NewProjectScreen())

    result = NewProjectApp().run()
    return pathlib.Path(result) if result else None


# ── Error screens ─────────────────────────────────────────────────────────────

def _run_error_screen(title: str, lines: list[str]) -> None:
    """Show a simple Textual error screen with a press-Enter-to-continue button."""
    from textual.app import App, ComposeResult
    from textual.binding import Binding
    from textual.containers import Vertical
    from textual.screen import Screen
    from textual.widgets import Button, Label

    class ErrorScreen(Screen):
        BINDINGS = [
            Binding("escape", "close", "Close", show=False),
            Binding("enter",  "close", "Close", show=False),
            Binding("q",      "close", "Close", show=False),
        ]

        DEFAULT_CSS = """
        ErrorScreen {
            align: center middle;
            background: #0d0d1a;
        }

        #err-box {
            width: 70;
            height: auto;
            border: solid #404060;
            padding: 1 2;
            background: #0d0d1a;
        }

        #err-title {
            color: #00d7ff;
            text-style: bold;
            margin-bottom: 1;
        }

        #err-divider {
            color: #404060;
            margin-bottom: 1;
        }

        .err-line {
            color: #505070;
            height: 1;
        }

        .err-line.code {
            color: #c0c0c0;
            text-style: bold;
        }

        #err-btn {
            margin-top: 1;
        }
        """

        def compose(self) -> ComposeResult:
            with Vertical(id="err-box"):
                yield Label(title, id="err-title")
                yield Label("\u2500" * 55, id="err-divider")
                for line in lines:
                    css_class = "err-line code" if line.startswith("  pip") or line.startswith("  altergo") else "err-line"
                    yield Label(line, classes=css_class)
                yield Button("Go back", variant="primary", id="err-btn")

        def on_button_pressed(self, event: Button.Pressed) -> None:
            if event.button.id == "err-btn":
                self.action_close()

        def action_close(self) -> None:
            self.app.exit(result=None)

    class ErrorApp(App):
        CSS = "Screen { background: #0d0d1a; }"

        def on_mount(self) -> None:
            self.push_screen(ErrorScreen())

    ErrorApp().run()


def _show_no_accounts(chosen_project: str) -> None:
    _run_error_screen(
        "rover  \u00b7  no altergo accounts",
        [
            f"No altergo accounts found for project: {chosen_project}",
            "",
            "Create an account first, then retry:",
            "",
            "  altergo --config",
            "  altergo --config mywork --provider claude",
            "  altergo --config gemini-dev --provider gemini",
            "",
            "Providers: claude  gemini  codex  copilot",
        ],
    )


def _show_altergo_not_found() -> None:
    _run_error_screen(
        "rover  \u00b7  altergo not found",
        [
            "altergo is not on PATH.",
            "",
            "Install it from:",
            "",
            "  pip install altergo",
            "  pipx install altergo",
            "",
            "Then retry.",
        ],
    )


def _show_no_sessions_for_account(account: str) -> None:
    _run_error_screen(
        "rover  \u00b7  no sessions",
        [
            f"No previous sessions found for: {account}",
            "",
            "Start one with A or Y first.",
        ],
    )


def _show_yolo_pick_no_sessions() -> None:
    _run_error_screen(
        "rover  \u00b7  yolo pick  (no sessions)",
        [
            "No sessions found.",
            "",
            "Press A to start one.",
        ],
    )


# ── Prompt attach-or-new (runs outside Textual using Rich) ────────────────────

def _prompt_attach_or_new(console: Console, session_name: str) -> str:
    """Modal prompt: Attach (default) / New instance / Cancel.

    Runs a short Textual app so the prompt matches the rest of rover's UI.
    The ``console`` argument is accepted for test-compat and ignored at
    runtime.  Returns 'attach', 'new', or 'cancel'.
    """
    from textual.app import App, ComposeResult
    from textual.binding import Binding
    from textual.containers import Vertical
    from textual.screen import Screen
    from textual.widgets import Label

    class AttachOrNewScreen(Screen):
        BINDINGS = [
            Binding("a",      "attach", "Attach", show=False),
            Binding("enter",  "attach", "Attach", show=False),
            Binding("n",      "new",    "New",    show=False),
            Binding("c",      "cancel", "Cancel", show=False),
            Binding("escape", "cancel", "Cancel", show=False),
            Binding("q",      "cancel", "Cancel", show=False),
        ]

        DEFAULT_CSS = """
        AttachOrNewScreen {
            align: center middle;
            background: #0d0d1a;
        }

        #aon-box {
            width: auto;
            min-width: 52;
            max-width: 80;
            height: auto;
            border: solid #404060;
            padding: 1 2;
            background: #0d0d1a;
        }

        #aon-title {
            text-style: bold;
            color: #00d7ff;
            margin-bottom: 1;
        }

        #aon-divider {
            color: #404060;
            margin-bottom: 1;
        }

        .aon-line {
            color: #c0c0e0;
            height: 1;
        }

        .aon-line.dim {
            color: #808080;
        }

        #aon-hint {
            margin-top: 1;
            color: #606080;
        }
        """

        def compose(self) -> ComposeResult:
            with Vertical(id="aon-box"):
                yield Label("Session already exists", id="aon-title")
                yield Label("\u2500" * 48, id="aon-divider")
                yield Label(
                    f"[bold]{session_name}[/bold] is already a tmux session.",
                    classes="aon-line",
                )
                yield Label(
                    "[dim]A[/dim]ttach  \u00b7  [dim]N[/dim]ew instance  "
                    "\u00b7  [dim]C[/dim]ancel",
                    classes="aon-line",
                )
                yield Label(
                    "[dim]Enter / a attach  \u00b7  n new  \u00b7  "
                    "c / Esc cancel[/dim]",
                    id="aon-hint",
                )

        def action_attach(self) -> None:
            self.app.exit(result="attach")

        def action_new(self) -> None:
            self.app.exit(result="new")

        def action_cancel(self) -> None:
            self.app.exit(result="cancel")

    class AttachOrNewApp(App):
        CSS = "Screen { background: #0d0d1a; }"

        def on_mount(self) -> None:
            self.push_screen(AttachOrNewScreen())

    result = AttachOrNewApp().run()
    if result in ("attach", "new", "cancel"):
        return result
    return "attach"


# ── Public entry point ────────────────────────────────────────────────────────

def run_altergo_launcher(
    config: dict,
    save_config_fn,
    *,
    yolo: bool = False,
    yolo_resume: bool | str = False,
    _project_path_override: str | None = None,
    _account_override: str | None = None,
) -> None:
    """Show workspace → project → account pickers then exec altergo.

    Parameters
    ----------
    config:
        The rover config dict (loaded via load_config()).  May be mutated
        to persist a newly entered workspace path.
    save_config_fn:
        Callable that atomically writes the config dict to disk.
    yolo:
        When True, append ``--yolo`` to the altergo argv.
    yolo_resume:
        When True, append ``--yolo-resume`` (no ID).
        When a UUID string, append ``--yolo-resume=<UUID>``.
    _project_path_override:
        Absolute path to use as the working directory, bypassing the project
        picker.
    _account_override:
        Account name to use directly, bypassing the account picker.

    Returns None — either because the user cancelled or because altergo
    has now exited.
    """
    console = Console()

    # Fast path: both overrides supplied — skip all pickers
    if _project_path_override and _account_override:
        _exec_altergo(
            console,
            project_path=pathlib.Path(_project_path_override),
            chosen_account=_account_override,
            chosen_provider=None,
            yolo=yolo,
            yolo_resume=yolo_resume,
        )
        return

    # yolo-resume-last (yolo_resume=True, no UUID): skip project picker
    if yolo_resume is True and not _project_path_override:
        accounts_data = _list_accounts_with_mtime()
        if accounts_data:
            account_names  = [name  for name, _     in accounts_data]
            account_mtimes = [mtime for _,    mtime in accounts_data]
            display_labels = []
            for name in account_names:
                provider  = _get_account_provider(name)
                label_pad = max(1, 24 - len(name))
                display_labels.append(
                    name + " " * label_pad + f"[dim][{provider}][/dim]"
                )
            account_names.append("native")
            account_mtimes.append(0.0)
            display_labels.append(
                "native" + " " * max(1, 24 - len("native")) + "[dim][real $HOME][/dim]"
            )
            chosen_account = _run_picker(
                "rover  \u00b7  pick an account  (yolo-resume-last)",
                account_names,
                subtitle="will resume last session",
                display_items=display_labels,
                sort_keys=account_mtimes,
            )
            if chosen_account is None:
                return
            chosen_provider = None
            if chosen_account == "native":
                chosen_provider = _run_picker(
                    "rover  \u00b7  pick a provider",
                    list(_KNOWN_PROVIDERS),
                    subtitle="native  \u00b7  real $HOME, no isolation",
                )
                if chosen_provider is None:
                    return

            from rover.sessions_index import list_altergo_sessions
            all_sessions = list_altergo_sessions()
            account_sessions = [
                s for s in all_sessions if s.account == chosen_account
            ]
            if not account_sessions:
                _show_no_sessions_for_account(chosen_account)
                return

            latest = account_sessions[0]
            _exec_altergo(
                console,
                project_path=pathlib.Path(latest.project_path),
                chosen_account=chosen_account,
                chosen_provider=chosen_provider,
                yolo=yolo,
                yolo_resume=latest.session_id,
            )
            return

    # ── Step 1: ensure workspace is configured ────────────────────────────────
    workspace = config.get("git_workspace", "").strip()
    if not workspace or not pathlib.Path(workspace).is_dir():
        new_ws = _run_workspace_prompt()
        if not new_ws:
            return
        config["git_workspace"] = new_ws
        save_config_fn(config)
        workspace = new_ws

    # ── Step 2: pick a project ────────────────────────────────────────────────
    projects_data = _list_git_projects_with_mtime(workspace)
    if not projects_data:
        _run_error_screen(
            "rover  \u00b7  no git repos",
            [
                f"No git repos found in {workspace}",
                "",
                "Subdirectories need a .git folder to appear here.",
            ],
        )
        return

    project_names  = [name  for name, _     in projects_data]
    project_mtimes = [mtime for _,    mtime in projects_data]

    # Prepend two action sentinels to the picker. pin_top_count=2 keeps them
    # on page 1 regardless of sort mode. display_items styles them distinctly
    # from real project rows so the user doesn't mistake them for repos.
    workspace_basename = pathlib.Path(workspace).name or workspace
    picker_items    = [_PROJECT_NEW, _PROJECT_WORKSPACE] + project_names
    picker_display  = [
        "[bold #00d7ff]+ create new project\u2026[/bold #00d7ff]",
        f"[#00d7ff]\u00b7[/#00d7ff] [dim]use workspace root[/dim]  "
        f"[dim]({workspace_basename})[/dim]",
    ] + project_names
    picker_mtimes   = [0.0, 0.0] + project_mtimes

    # ── State machine: project → account → (provider if native) → exec ────────
    # Each step can return to the previous one via q/Backspace (the pickers
    # launched with back_enabled=True). Esc still exits the whole flow.
    # The project picker is the first step so it has back_enabled=False —
    # q/Backspace there behave like cancel.
    step: str = "project"
    project_path: pathlib.Path | None = None
    chosen_account: str | None = None
    chosen_provider: str | None = None

    while True:
        if step == "project":
            chosen_project = _run_picker(
                "rover  \u00b7  pick a project",
                picker_items,
                subtitle=workspace,
                display_items=picker_display,
                sort_keys=picker_mtimes,
                pin_top_count=2,
                back_enabled=False,
            )
            if chosen_project is None or chosen_project == _PICKER_BACK:
                return

            if chosen_project == _PROJECT_NEW:
                new_path = _run_new_project_prompt(workspace)
                if new_path is None:
                    # Cancelled the name prompt — stay on the project picker
                    # instead of exiting the whole flow.
                    continue
                project_path = new_path
            elif chosen_project == _PROJECT_WORKSPACE:
                project_path = pathlib.Path(workspace)
            else:
                project_path = pathlib.Path(workspace) / chosen_project

            step = "account"
            continue

        if step == "account":
            assert project_path is not None

            if _account_override:
                chosen_account = _account_override
                chosen_provider = None
                break

            accounts_data = _list_accounts_with_mtime()
            if not accounts_data:
                _show_no_accounts(project_path.name)
                return

            account_names  = [name  for name, _     in accounts_data]
            account_mtimes = [mtime for _,    mtime in accounts_data]

            display_labels = []
            for name in account_names:
                provider  = _get_account_provider(name)
                label_pad = max(1, 24 - len(name))
                display_labels.append(
                    name + " " * label_pad + f"[dim][{provider}][/dim]"
                )

            account_names.append("native")
            account_mtimes.append(0.0)
            display_labels.append(
                "native" + " " * max(1, 24 - len("native")) + "[dim][real $HOME][/dim]"
            )

            chosen_account = _run_picker(
                "rover  \u00b7  pick an account",
                account_names,
                subtitle=f"project: {project_path.name}",
                display_items=display_labels,
                sort_keys=account_mtimes,
                back_enabled=True,
            )
            if chosen_account is None:
                return
            if chosen_account == _PICKER_BACK:
                step = "project"
                continue

            if chosen_account == "native":
                step = "provider"
                continue

            chosen_provider = None
            break

        if step == "provider":
            assert project_path is not None
            chosen_provider = _run_picker(
                "rover  \u00b7  pick a provider",
                list(_KNOWN_PROVIDERS),
                subtitle="native  \u00b7  real $HOME, no isolation",
                back_enabled=True,
            )
            if chosen_provider is None:
                return
            if chosen_provider == _PICKER_BACK:
                step = "account"
                continue
            break

    # ── Step 4: hand off to altergo ───────────────────────────────────────────
    assert project_path is not None and chosen_account is not None
    _exec_altergo(
        console,
        project_path=project_path,
        chosen_account=chosen_account,
        chosen_provider=chosen_provider,
        yolo=yolo,
        yolo_resume=yolo_resume,
    )


def _exec_altergo(
    console: Console,
    *,
    project_path: pathlib.Path,
    chosen_account: str,
    chosen_provider: str | None,
    yolo: bool,
    yolo_resume: bool | str,
) -> None:
    """Build the altergo argv and run it as a child process."""
    import shutil

    provider_label = chosen_provider if chosen_provider else _get_account_provider(chosen_account)
    mode_hint = ""
    if yolo_resume:
        mode_hint = "  [dim]\u00b7 yolo-resume[/dim]"
    elif yolo:
        mode_hint = "  [dim]\u00b7 yolo[/dim]"

    try:
        console.print(
            f"\n  [bold {_CYAN}]\u2192 launching altergo[/bold {_CYAN}]"
            f"  [dim]\u00b7 {chosen_account} [{provider_label}][/dim]"
            f"  [dim]\u00b7 {project_path.name}[/dim]"
            + mode_hint
        )
    except Exception:
        pass

    altergo_bin = shutil.which("altergo")
    if not altergo_bin:
        _show_altergo_not_found()
        return

    if chosen_provider:
        argv = [altergo_bin, "native", chosen_provider]
    else:
        argv = [altergo_bin, chosen_account]

    if yolo_resume and isinstance(yolo_resume, str):
        argv.append(f"--yolo-resume={yolo_resume}")
    elif yolo_resume:
        argv.append("--yolo-resume")
    elif yolo:
        argv.append("--yolo")

    from rover.config import load_config
    from rover import session_manager

    cfg = load_config()
    wrap_tmux = bool(cfg.get("wrap_tmux", True))
    inside_tmux = bool(os.environ.get("TMUX"))

    if wrap_tmux and not inside_tmux and session_manager.is_available():
        provider_for_name = chosen_provider or _get_account_provider(chosen_account)
        base_name = _derive_session_name(project_path, chosen_account, provider_for_name)

        session_name: str | None = base_name
        if session_manager.has_session(base_name):
            choice = _prompt_attach_or_new(console, base_name)
            if choice == "cancel":
                return
            if choice == "new":
                session_name = session_manager.unique_session_name(base_name)
            else:
                try:
                    console.print(
                        f"  [dim]\u00b7 attaching to existing session "
                        f"[bold]{base_name}[/bold][/dim]"
                    )
                except Exception:
                    pass
                session_manager.attach_session(base_name)
                return

        cwd = str(project_path) if project_path.is_dir() else None
        try:
            console.print(
                f"  [dim]\u00b7 tmux session: [bold]{session_name}[/bold] "
                f"(detach: Ctrl-b d)[/dim]"
            )
        except Exception:
            pass

        session_manager.new_attached_session(session_name, cwd=cwd, cmd=argv)
        try:
            console.print("[dim]  \u00b7 returned from altergo[/dim]")
        except Exception:
            pass
        return

    _run_altergo_direct(console, argv, project_path)


def _run_altergo_direct(
    console: Console,
    argv: list[str],
    project_path: pathlib.Path,
) -> None:
    """Run altergo in the caller's own process, chdir'd to the project path."""
    original_cwd: str | None = None
    if project_path.is_dir():
        try:
            original_cwd = os.getcwd()
            os.chdir(project_path)
        except OSError:
            original_cwd = None

    try:
        subprocess.run(argv)
    finally:
        if original_cwd is not None:
            try:
                os.chdir(original_cwd)
            except OSError:
                pass
        try:
            console.print("[dim]  \u00b7 returned from altergo[/dim]")
        except Exception:
            pass


def run_yolo_resume_pick(config: dict, save_config_fn) -> None:
    """Cross-account session picker → yolo-resume by session ID."""
    from rover.sessions_index import list_altergo_sessions
    from rover.telemetry import _emit
    import datetime as _dt

    sessions = list_altergo_sessions()
    if not sessions:
        _show_yolo_pick_no_sessions()
        return

    items: list[str] = []
    display_items: list[str] = []
    sort_keys: list[float] = []

    for rec in sessions:
        key = f"{rec.session_id}|{rec.project_path}|{rec.account}|{rec.provider}"
        items.append(key)
        sort_keys.append(rec.modified_at)

        proj_name = pathlib.Path(rec.project_path).name if rec.project_path else "?"
        proj_col = proj_name[:16].ljust(16)
        acct_col = rec.account[:12].ljust(12)
        try:
            date_col = _dt.datetime.fromtimestamp(rec.modified_at).strftime("%m-%d")
        except Exception:
            date_col = "?????"
        date_col = date_col[:5].ljust(5)
        preview_col = (rec.preview or f"[{rec.provider}]")[:28]
        display_items.append(
            f"[bold]{proj_col}[/bold]  [dim]{acct_col}[/dim]  [dim]{date_col}[/dim]  {preview_col}"
        )

    chosen = _run_picker(
        "rover  \u00b7  yolo pick session",
        items,
        subtitle="select to resume with --yolo-resume",
        display_items=display_items,
        sort_keys=sort_keys,
    )
    if chosen is None:
        return

    parts = chosen.split("|", 3)
    if len(parts) != 4:
        return
    session_id, project_path, account, provider = parts

    _emit({
        "event": "launch",
        "mode": "yolo_resume",
        "provider": provider,
        "account": account,
        "session_id": session_id,
    })

    run_altergo_launcher(
        config,
        save_config_fn,
        yolo_resume=session_id,
        _project_path_override=project_path if project_path else None,
        _account_override=account,
    )
