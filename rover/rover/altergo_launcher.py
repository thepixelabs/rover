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

run_native_ssh_setup(console=None)
  Non-interactive setup command. Not touched.
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

_ALTERGO_DIR   = pathlib.Path.home() / ".altergo"
_ACCOUNTS_DIR  = _ALTERGO_DIR / "accounts"
_DIM_BORDER    = "#404060"
_CYAN          = "#00d7ff"

_LETTERS   = string.ascii_lowercase
_PAGE_SIZE = 26

_KNOWN_PROVIDERS = ("claude", "gemini", "codex", "copilot")


# ── Native SSH bridge ─────────────────────────────────────────────────────────

def _real_home() -> pathlib.Path:
    """Real user home, ignoring altergo's HOME swap."""
    try:
        import pwd
        return pathlib.Path(pwd.getpwuid(os.getuid()).pw_dir)
    except Exception:
        return pathlib.Path.home()


def _native_ssh_token_path() -> pathlib.Path:
    return _real_home() / ".claude" / "rover-native-token"


def _check_native_ssh_token(console: Console) -> bool:
    """True if native account will work here, False if SSH + token missing."""
    if not os.environ.get("SSH_CONNECTION"):
        return True

    token_path = _native_ssh_token_path()
    try:
        size = token_path.stat().st_size if token_path.exists() else 0
    except OSError:
        size = 0

    if size > 0:
        return True

    console.print(
        "\n  [bold yellow]native account not available over SSH[/bold yellow]\n"
        "  [dim]Claude Code reads native-account credentials from the macOS\n"
        "  Keychain, which is locked for SSH sessions.[/dim]\n\n"
        "  [bold]Fix — works from SSH too:[/bold]\n"
        "    rover --setup-native-ssh\n\n"
        f"  [dim]Generates a long-lived OAuth token (via [bold]claude\n"
        f"  setup-token[/bold], which prints a URL you open in your phone\n"
        f"  browser — no local browser needed) and writes it to\n  {token_path}\n"
        "  which SSH sessions export automatically.[/dim]\n"
    )
    try:
        console.input("  [dim]press Enter to return to menu…[/dim] ")
    except (EOFError, KeyboardInterrupt):
        pass
    return False


def run_native_ssh_setup(console: Console | None = None) -> int:
    """Bootstrap the Claude native OAuth token for SSH use. Returns exit code."""
    import shutil

    if console is None:
        console = Console()

    claude_bin = shutil.which("claude")
    if not claude_bin:
        console.print(
            "\n  [red]claude CLI not found on PATH.[/red]\n"
            "  [dim]Install Claude Code first: https://claude.com/code[/dim]\n"
        )
        return 2

    over_ssh = bool(os.environ.get("SSH_CONNECTION"))
    console.print(
        "\n  [bold cyan]Generating a long-lived Claude OAuth token[/bold cyan]\n"
        + (
            "  [dim]You're over SSH — claude setup-token will print a URL.\n"
            "  Open it in your phone's browser, approve, and paste the token\n"
            "  back here when it prints to the terminal.[/dim]\n"
            if over_ssh
            else
            "  [dim]A browser window will open for confirmation. After the token\n"
            "  prints to the terminal, copy it and paste it when prompted below.[/dim]\n"
        )
    )

    try:
        subprocess.run([claude_bin, "setup-token"])
    except KeyboardInterrupt:
        console.print("\n  [yellow]cancelled[/yellow]\n")
        return 1
    except Exception as exc:  # noqa: BLE001
        console.print(f"\n  [red]claude setup-token failed: {exc}[/red]\n")
        return 1

    console.print(
        "\n  [bold]Paste the token below[/bold] [dim](starts with sk-ant-oat01-…):[/dim]"
    )
    try:
        raw = console.input("  token: ")
    except (EOFError, KeyboardInterrupt):
        console.print("\n  [yellow]cancelled[/yellow]\n")
        return 1

    token = "".join(raw.split())
    if not token.startswith("sk-ant-oat01-"):
        console.print(
            "\n  [red]Token doesn't look right (expected sk-ant-oat01-… prefix).[/red]\n"
            "  [dim]Nothing was written. Try again.[/dim]\n"
        )
        return 1

    token_path = _native_ssh_token_path()
    try:
        token_path.parent.mkdir(parents=True, exist_ok=True)
        token_path.write_text(token, encoding="utf-8")
        os.chmod(token_path, 0o600)
    except OSError as exc:
        console.print(f"\n  [red]failed to write token file: {exc}[/red]\n")
        return 1

    console.print(
        f"\n  [green]\u2713 token saved[/green]   [dim]{token_path}[/dim]\n"
        "  [dim]chmod 600. SSH sessions will now use the native account.\n"
        "  If Claude ever invalidates this token, rerun this command.[/dim]\n"
    )
    return 0


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
) -> str | None:
    """Show a letter-keyed paginated Textual picker. Returns selected item or None."""
    from textual.app import App, ComposeResult
    from textual.binding import Binding
    from textual.containers import Vertical
    from textual.screen import Screen
    from textual.widgets import DataTable, Label, Static

    if not items:
        return None

    display = display_items if display_items is not None else items

    class PickerScreen(Screen):
        BINDINGS = [
            Binding("escape", "cancel", "Cancel", show=False),
            Binding("q",      "cancel", "Cancel", show=False),
            Binding("ctrl+c", "cancel", "Cancel", show=False),
            Binding("]",      "next_page",  "Next",  show=False),
            Binding("[",      "prev_page",  "Prev",  show=False),
            Binding("right",  "next_page",  "Next",  show=False),
            Binding("left",   "prev_page",  "Prev",  show=False),
        ] + [
            Binding(ch, f"pick_letter('{ch}')", "", show=False)
            for ch in _LETTERS
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
        }

        #picker-box {
            width: 80%;
            min-width: 40;
            max-width: 90;
            height: auto;
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
            background: #0d0d1a;
        }

        #picker-hint {
            color: #404060;
            height: 1;
            padding-bottom: 1;
        }
        """

        def __init__(self) -> None:
            super().__init__()
            self._page = 0
            self._sort = "name"

        def _sorted_indices(self) -> list[int]:
            if self._sort == "modified" and sort_keys is not None:
                return sorted(range(len(items)), key=lambda i: -(sort_keys[i] or 0.0))
            return sorted(range(len(items)), key=lambda i: items[i].lower())

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
                hint_parts = ["  a\u2013z select"]
                if total > 1:
                    hint_parts.append(
                        f"  \u00b7  ] next  [ prev"
                        f"  \u00b7  page {self._page + 1}/{total}"
                    )
                if sort_keys is not None:
                    hint_parts.append("  \u00b7  s sort")
                hint_parts.append("  \u00b7  q cancel")
                self.query_one("#picker-hint", Label).update(
                    "[dim]" + "".join(hint_parts) + "[/dim]"
                )
            except Exception:
                pass

        def action_cancel(self) -> None:
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
            self.cursor_type = "none"
            self.show_cursor = False

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
    from textual.widgets import Button, Input, Label, Static

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
            width: 70;
            height: auto;
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


# ── Error screens ─────────────────────────────────────────────────────────────

def _run_error_screen(title: str, lines: list[str]) -> None:
    """Show a simple Textual error screen with a press-Enter-to-continue button."""
    from textual.app import App, ComposeResult
    from textual.binding import Binding
    from textual.containers import Vertical
    from textual.screen import Screen
    from textual.widgets import Button, Label, Static

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
    """Inline prompt: Attach (default) / New instance / Cancel.

    Runs outside Textual using a simple Rich console.input() call.
    Returns 'attach', 'new', or 'cancel'.
    """
    console.print(
        f"\n  [bold {_CYAN}]\u21ba[/bold {_CYAN}] tmux session "
        f"[bold]{session_name}[/bold] already exists."
    )
    try:
        raw = console.input(
            "  [dim][A][/dim]ttach  \u00b7  [dim][N][/dim]ew instance  \u00b7  "
            "[dim][C][/dim]ancel  [dim](default: A)[/dim]: "
        ).strip().lower()
    except (EOFError, KeyboardInterrupt):
        raw = "a"

    if raw.startswith("n"):
        return "new"
    if raw.startswith("c"):
        return "cancel"
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
        console.print(
            f"\n  [yellow]No git repos found in[/yellow] [bold]{workspace}[/bold]\n"
            "  [dim]Subdirectories need a .git folder to appear here.[/dim]\n\n"
            "  [dim]Press Enter to continue.[/dim]"
        )
        try:
            input()
        except (EOFError, KeyboardInterrupt):
            pass
        return

    project_names  = [name  for name, _     in projects_data]
    project_mtimes = [mtime for _,    mtime in projects_data]

    chosen_project = _run_picker(
        "rover  \u00b7  pick a project",
        project_names,
        subtitle=workspace,
        sort_keys=project_mtimes,
    )
    if chosen_project is None:
        return

    project_path = pathlib.Path(workspace) / chosen_project

    # ── Step 3: pick an account ───────────────────────────────────────────────
    if _account_override:
        chosen_account = _account_override
        chosen_provider = None
    else:
        accounts_data = _list_accounts_with_mtime()

        if not accounts_data:
            _show_no_accounts(chosen_project)
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

    # ── Step 4: hand off to altergo ───────────────────────────────────────────
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

    if chosen_account == "native" and not _check_native_ssh_token(console):
        return

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

        acct_col = rec.account[:14].ljust(14)
        try:
            date_col = _dt.datetime.fromtimestamp(rec.modified_at).strftime("%Y-%m-%d")
        except Exception:
            date_col = "???????????"
        date_col = date_col[:10].ljust(10)
        preview_col = (rec.preview or f"[{rec.provider}]")[:30]
        display_items.append(
            f"[dim]{acct_col}[/dim]  [dim]{date_col}[/dim]  {preview_col}"
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
