"""Config management for rover.

Config file lives at ~/.rover/config.json.
The directory and file are created on first run if missing.
Writes are atomic: tmp file + os.replace, same pattern as altergo.
"""

import json
import os
import pathlib

CONFIG_DIR = pathlib.Path.home() / ".rover"
CONFIG_FILE = CONFIG_DIR / "config.json"
_CONFIG_TMP = CONFIG_DIR / "config.json.tmp"

# ── One-time migration from old ~/.dispatch-tui/config.json ──────────────────
_OLD_CONFIG = pathlib.Path.home() / ".dispatch-tui" / "config.json"

DEFAULT_CONFIG: dict = {
    "nickname": "",           # empty = use os.getlogin()
    "time_window_hours": 2,
    "refresh_seconds": 30,
    "theme": "cyber",         # cyber | sunset | ocean | mono
    "show_tmux": True,
    "show_nickname_in_header": True,  # big figlet: nickname (on) vs "rover" (off)
    "dispatch_port": 4242,
    "git_workspace": "",      # path to git projects root (used by altergo launcher)
    "header_font": "thin",    # pyfiglet font for the rover banner / menu header
    "animation_pack": "dots", # rich spinner name for loading indicators
    "dispatch_repo_path": "", # path to the dispatch repo (for `B` start/stop). Empty = auto-detect.
    "wrap_tmux": True,        # wrap altergo launches in a rover-named tmux session (project/account/provider)
}


def _ensure_config_dir() -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)


def _migrate_old_config() -> None:
    """Copy ~/.dispatch-tui/config.json to ~/.rover/config.json once, if needed."""
    if CONFIG_FILE.exists() or not _OLD_CONFIG.exists():
        return
    try:
        import shutil
        _ensure_config_dir()
        shutil.copy2(_OLD_CONFIG, CONFIG_FILE)
    except OSError:
        pass


def load_config() -> dict:
    """Return merged dict of defaults + saved values.

    On first run after upgrading from dtui, automatically migrates the old
    ~/.dispatch-tui/config.json to ~/.rover/config.json so settings are
    preserved without any manual intervention.

    Missing keys fall back to DEFAULT_CONFIG so callers always see the
    full schema even if the on-disk file predates a new key.
    """
    _migrate_old_config()
    _ensure_config_dir()

    saved: dict = {}
    if CONFIG_FILE.exists():
        try:
            with CONFIG_FILE.open("r", encoding="utf-8") as fh:
                saved = json.load(fh)
        except (json.JSONDecodeError, OSError):
            # Corrupt or unreadable — start fresh rather than crashing.
            saved = {}

    merged = {**DEFAULT_CONFIG, **saved}

    # Persist back if file was missing or gained new default keys.
    if not CONFIG_FILE.exists() or saved != merged:
        save_config(merged)

    return merged


def save_config(cfg: dict) -> None:
    """Atomically write cfg to disk.

    Writes to a .tmp file first, then renames, so a crash mid-write
    never leaves a half-written config.
    """
    _ensure_config_dir()

    with _CONFIG_TMP.open("w", encoding="utf-8") as fh:
        json.dump(cfg, fh, indent=2)
        fh.write("\n")

    os.replace(_CONFIG_TMP, CONFIG_FILE)


def get_nickname() -> str:
    """Return the user's display name.

    Falls back to os.getlogin() if nickname is empty or getlogin() raises.
    """
    cfg = load_config()
    nickname = cfg.get("nickname", "").strip()
    if nickname:
        return nickname
    try:
        return os.getlogin()
    except OSError:
        return os.environ.get("USER", os.environ.get("USERNAME", "agent"))
