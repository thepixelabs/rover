"""Banner and welcome message for rover.

Printed to stdout before the interactive menu starts so the user sees a
polished splash while the app initialises.

All heavy imports (rich, pyfiglet, rich_pyfiglet) are deferred into
function bodies so the module stays importable even when those packages
are absent — it degrades gracefully to plain-text output.
"""

from __future__ import annotations

import os
import sys


def _probe_cols(default: int = 80) -> int:
    """Live terminal width via TIOCGWINSZ. Single read, no retry."""
    for fd in (sys.stdout.fileno(), sys.stderr.fileno(), 0):
        try:
            return os.get_terminal_size(fd).columns
        except (OSError, ValueError):
            continue
    return default


def _await_true_width(
    timeout_s: float = 0.3,
    interval_s: float = 0.05,
    suspect: int = 80,
    default: int = 80,
) -> int:
    """Probe terminal width with a short retry loop, tolerating the SSH
    pty-req / window-change race on mobile SSH clients (Termius on Android
    is the canonical culprit).

    Sequence on every Termius first-open:
      1. SSH allocates a PTY; kernel winsize defaults to 80x24.
      2. Rover's banner starts rendering immediately.
      3. A few tens of ms later, Termius sends SSH `window-change` with the
         real dimensions, kernel updates winsize, SIGWINCH fires.

    If we probe at step 2 we get 80; if we probe at step 3+ we get truth.
    So: poll every ``interval_s`` up to ``timeout_s`` total. Return as soon
    as the probe is not the suspect 80-col default. Falls through with
    whatever value we last read (typically 80, safe graceful degradation).

    The 80-col sentinel is a heuristic — any real Termius window on a
    modern Android device renders wider than 80 at default font size, so
    "exactly 80" is statistically a stale winsize, not a real narrow window.
    """
    import time as _t

    deadline = _t.monotonic() + timeout_s
    last = _probe_cols(default)
    while last == suspect and _t.monotonic() < deadline:
        _t.sleep(interval_s)
        last = _probe_cols(default)
    return last

# ── Theme definitions ──────────────────────────────────────────────────────────
#
# Each theme maps to a 2-6 stop gradient expressed as hex colour strings.
# The same palette is reused for the figlet banner and inline text colouring.

THEMES: dict[str, list[str]] = {
    "cyber":    ["#00d7ff", "#af00ff"],           # cyan  → purple
    "sunset":   ["#ffaf5f", "#ff5f87"],           # amber → rose
    "ocean":    ["#00d7ff", "#005fd7"],           # cyan  → blue
    "mono":     ["#ffffff", "#808080"],           # white → grey
    "forest":   ["#5fff87", "#005f5f"],           # mint  → teal
    "lavender": ["#d7afff", "#5f5fff"],           # lilac → indigo
    "rainbow":  ["#ff005f", "#ff8700", "#ffff00", "#00ff5f", "#00d7ff", "#af5fff"],
}

# ── Configurable header fonts (small / compact only) ─────────────────────────
#
# Only fonts that render legibly in ~80 columns are listed here.  These map
# 1-to-1 to the select options shown in the settings screen.

HEADER_FONTS: list[tuple[str, str]] = [
    ("smslant  (default)",  "smslant"),
    ("thin",                "thin"),
    ("small",               "small"),
    ("mini",                "mini"),
    ("digital",             "digital"),
    ("banner",              "banner"),
    ("smshadow",            "smshadow"),
]

# ── Animation packs (rich spinner names) ─────────────────────────────────────

ANIMATION_PACKS: list[tuple[str, str]] = [
    ("dots     (default)",  "dots"),
    ("star",                "star"),
    ("star2",               "star2"),
    ("line",                "line"),
    ("arc",                 "arc"),
    ("moon",                "moon"),
    ("bounce",              "bounce"),
]

_DEFAULT_FONT = "smslant"
_BANNER_TEXT  = "rover"


# ── Helpers ────────────────────────────────────────────────────────────────────

def _mid_color(theme: str) -> str:
    """Return an approximate midpoint hex colour for a theme gradient."""
    colors = THEMES.get(theme, THEMES["cyber"])

    def _parse(h: str) -> tuple[int, int, int]:
        h = h.lstrip("#")
        return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)

    # Average first and last stop
    r1, g1, b1 = _parse(colors[0])
    r2, g2, b2 = _parse(colors[-1])
    return f"#{(r1 + r2) // 2:02x}{(g1 + g2) // 2:02x}{(b1 + b2) // 2:02x}"


def clear_screen() -> None:
    """Clear the terminal using ANSI escape codes."""
    print("\033[2J\033[H", end="", flush=True)


# ── Public API ─────────────────────────────────────────────────────────────────

def show_banner(
    nickname: str,
    greeting: tuple[str, str],
    theme: str = "cyber",
    font: str = _DEFAULT_FONT,
    animation_pack: str = "dots",
) -> None:
    """Print the rover banner + greeting to stdout with an optional startup spin.

    Layout
    ------
    ① Brief loading spinner (using animation_pack) while the banner renders.
    ② Figlet "rover" in the theme gradient (font is user-configurable).
    ③ Blank line.
    ④ "Welcome back, {nickname} — {emoji} {greeting_text}"  (gradient coloured).

    Falls back gracefully to plain text if pyfiglet / rich_pyfiglet are absent.

    Parameters
    ----------
    nickname:
        The user's display name (from config or os.getlogin()).
    greeting:
        (emoji, text) tuple from greetings.pick_greeting().
    theme:
        Key into THEMES — controls gradient colours.
    font:
        Pyfiglet font name — should be one of the HEADER_FONTS entries.
    animation_pack:
        Rich spinner name used for the startup loading indicator.
    """
    emoji_str, greeting_text = greeting
    mid_color = _mid_color(theme)
    colors = THEMES.get(theme, THEMES["cyber"])

    # Validate font — fall back to default if unknown
    known_fonts = {f for _, f in HEADER_FONTS}
    if font not in known_fonts:
        font = _DEFAULT_FONT

    try:
        from rich.console import Console
        from rich.live import Live
        from rich.spinner import Spinner
        from rich.text import Text
        from rich_pyfiglet import RichFiglet  # type: ignore[import]

        # Await the real terminal width before rendering. Mobile SSH clients
        # (Termius) defer the window-change message, so an immediate probe
        # returns 80x24 even when the real window is wider. _await_true_width
        # polls for up to 300ms, which overlaps the 350ms startup spinner
        # below anyway — no added user-perceived latency on fast clients.
        width = _await_true_width()
        # IMPORTANT: do NOT pass width= to Console. Rich's Console caches any
        # explicit width permanently; a stale snapshot here would lock the
        # entire TUI to the wrong size. Let Rich re-probe via its default
        # mechanism on each render, and use ``width`` only for our own
        # centering math.
        console = Console()

        # ── Startup spinner (very brief — gives a snappy "loading" feel) ──────
        spinner = Spinner(animation_pack, text="  loading rover...", style="dim", speed=1.2)
        with Live(spinner, console=console, refresh_per_second=15, transient=True):
            import time as _t
            _t.sleep(0.35)

        # ── Figlet banner ─────────────────────────────────────────────────────
        fig = RichFiglet(
            _BANNER_TEXT,
            font=font,
            colors=colors,
            justify="center",
        )
        console.print(fig)

        # ── Blank separator ───────────────────────────────────────────────────
        console.print()

        # ── Welcome line ──────────────────────────────────────────────────────
        line = Text(justify="center")
        line.append(f"Welcome back, {nickname} \u2014 ")
        line.append(f"{emoji_str} {greeting_text}", style=f"bold {mid_color}")

        padding = max(0, (width - len(line.plain)) // 2)
        padded = Text(" " * padding)
        padded.append_text(line)
        console.print(padded)

    except Exception:
        # Graceful degradation — rich / rich_pyfiglet unavailable or font not
        # found.  A plain-text splash is always better than a traceback.
        print()
        print("  rover")
        print()
        print(f"  Welcome back, {nickname} \u2014 {emoji_str} {greeting_text}")
        print()
