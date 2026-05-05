#!/usr/bin/env python3
"""rover — on-the-go companion for dispatch agents."""

from __future__ import annotations

import argparse
import os
import sys


# ── PATH helper ────────────────────────────────────────────────────────────────

def _check_path(config: dict, save_config) -> None:
    """First-run helper: offer to add ~/.local/bin to ~/.zshrc if rover is not in PATH."""
    import shutil
    from rich.console import Console

    console = Console()

    if shutil.which("rover") is not None:
        config["path_prompt_answered"] = True
        save_config(config)
        return

    console.print(
        "\n[bold]rover[/bold] is not in your PATH."
    )
    try:
        answer = console.input(
            "Add pipx bin dir to ~/.zshrc now? [Y/n]: "
        ).strip().lower()
    except (EOFError, KeyboardInterrupt):
        answer = "n"

    config["path_prompt_answered"] = True
    save_config(config)

    if answer in ("", "y"):
        import glob
        import pathlib

        # Prefer ~/.local/bin (Linux / pipx default), then macOS user site.
        candidate = pathlib.Path.home() / ".local" / "bin"
        if not candidate.is_dir():
            pattern = str(pathlib.Path.home() / "Library" / "Python" / "*" / "bin")
            matches = sorted(glob.glob(pattern))
            if matches:
                candidate = pathlib.Path(matches[-1])

        bin_dir = str(candidate)
        zshrc = pathlib.Path.home() / ".zshrc"

        export_line = f'export PATH="{bin_dir}:$PATH"  # rover\n'

        # Only append if the line isn't already present.
        existing = zshrc.read_text(encoding="utf-8") if zshrc.exists() else ""
        if export_line.strip() not in existing:
            with zshrc.open("a", encoding="utf-8") as fh:
                fh.write(export_line)
            console.print(
                f"[green]Added[/green] {export_line.strip()}\n"
                "Run: [bold]source ~/.zshrc[/bold]  (or open a new terminal)\n"
            )
        else:
            console.print("[dim]Already present in ~/.zshrc — nothing changed.[/dim]\n")


# ── Dispatch helpers ───────────────────────────────────────────────────────────

def _run_dispatch(config: dict, hours: float) -> None:
    os.environ["DTUI_IN_TEXTUAL"] = "1"
    try:
        from rover.app import DispatchTuiApp
        DispatchTuiApp(hours=float(hours)).run()
    finally:
        os.environ.pop("DTUI_IN_TEXTUAL", None)


def _run_settings(config: dict, hours: float) -> None:
    os.environ["DTUI_IN_TEXTUAL"] = "1"
    try:
        from rover.app import DispatchTuiApp
        app = DispatchTuiApp(hours=float(hours))
        app._start_on_settings = True
        app.run()
    finally:
        os.environ.pop("DTUI_IN_TEXTUAL", None)


# ── Entry point ────────────────────────────────────────────────────────────────

def main() -> None:
    from rover import __version__

    parser = argparse.ArgumentParser(prog="rover")
    parser.add_argument(
        "--version",
        action="version",
        version=f"rover {__version__}",
    )
    parser.add_argument(
        "--hours",
        type=int,
        default=None,
        help="time window for agent dashboard in hours",
    )
    parser.add_argument(
        "--no-path-check",
        action="store_true",
        help="skip PATH check on startup",
    )
    args = parser.parse_args()

    # Load config
    from rover.config import load_config, get_nickname, save_config
    config = load_config()

    hours = args.hours if args.hours is not None else config.get("time_window_hours", 2)

    # PATH check (first run only)
    if not args.no_path_check and not config.get("path_prompt_answered", False):
        _check_path(config, save_config)

    # Git workspace onboarding (first run only).
    # Lazy fallback still exists inside altergo/yolo flows — this just nudges
    # the user to configure it once on first launch so yolo/altergo don't
    # pop a workspace prompt mid-session-creation. Esc is honored as "later"
    # and we flag it so we don't nag on every launch.
    if (
        not config.get("workspace_prompt_answered", False)
        and not config.get("git_workspace", "").strip()
    ):
        try:
            from rover.altergo_launcher import _run_workspace_prompt
            ws = _run_workspace_prompt()
            if ws:
                config["git_workspace"] = ws
            config["workspace_prompt_answered"] = True
            save_config(config)
        except Exception:
            # Never block launch on onboarding failure.
            pass

    # Check for an interactive terminal early — before the banner wastes time.
    # Without a PTY (e.g. SSH without -t), both stdin and /dev/tty will fail.
    import termios, io as _io
    _has_tty = False
    try:
        _fd = sys.stdin.fileno()
        termios.tcgetattr(_fd)
        _has_tty = True
    except (termios.error, OSError):
        try:
            with open("/dev/tty", "r+b", buffering=0):
                _has_tty = True
        except OSError:
            pass
    if not _has_tty:
        from rich.console import Console as _C
        _C().print(
            "[bold red]rover requires an interactive terminal (TTY).[/bold red]\n"
            "[dim]Your SSH session has no PTY allocated.\n"
            "  • Terminus: open connection settings → enable [bold]Request PTY[/bold]\n"
            "  • Command line: reconnect with [bold]ssh -t user@host[/bold][/dim]"
        )
        sys.exit(1)

    # Check tmux is installed
    from rover.session_manager import is_available
    if not is_available():
        from rich.console import Console
        console = Console()
        console.print("[bold red]tmux is not installed.[/bold red]")
        console.print("Install it with: [bold]brew install tmux[/bold]")
        sys.exit(1)

    # Main loop — the Textual MainMenuScreen renders its own figlet, greeting,
    # and clock internally, so we skip the standalone Rich banner that used to
    # run here. Rendering both caused a visible overlap (banner printed to
    # scrollback, Textual then drew its panel on top of the same rows).
    from rover.menu import run_menu, MenuAction

    while True:
        action = run_menu(config, hours=float(hours))

        if action == MenuAction.QUIT:
            break
        elif action == MenuAction.DISPATCH:
            _run_dispatch(config, hours)
        elif action == MenuAction.SETTINGS:
            _run_settings(config, hours)
            config = load_config()
        # If attach was selected, run_menu returned after the user detached from tmux.
        # The while loop re-enters the menu so the user can pick another action.


if __name__ == "__main__":
    main()
