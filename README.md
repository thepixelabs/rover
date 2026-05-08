# Rover

[![PyPI version](https://img.shields.io/pypi/v/rover-tui.svg)](https://pypi.org/project/rover-tui/)
[![GitHub release](https://img.shields.io/github/v/release/thepixelabs/rover)](https://github.com/thepixelabs/rover/releases)
[![License](https://img.shields.io/github/license/thepixelabs/rover)](LICENSE)
[![Tests](https://github.com/thepixelabs/rover/actions/workflows/ci.yml/badge.svg)](https://github.com/thepixelabs/rover/actions/workflows/ci.yml)

The Dispatch TUI — SSH into your Mac from your phone and check, launch, or kill any agent.

Landing page: https://rover.pixelabs.net

## What Rover is

Rover is a terminal companion for [Dispatch](https://github.com/thepixelabs/dispatch). It runs on
your Mac (or a Linux host), and you reach it over SSH from a phone or tablet to see which agents
are running, start new ones, and kill the ones that aren't.

## Prerequisites

- macOS or Linux (no Windows — use WSL)
- Python 3.11+
- tmux

## Install

### Homebrew (macOS, primary)

```bash
brew install thepixelabs/tap/rover
```

### pipx (any platform with Python)

```bash
pipx install rover-tui
```

### uv (modern pip alternative)

```bash
uv tool install rover-tui
```

## Update

### Homebrew

```bash
brew upgrade thepixelabs/tap/rover
```

### pipx

```bash
pipx upgrade rover-tui
```

### uv

```bash
uv tool upgrade rover-tui
```

## Uninstall

### Homebrew

```bash
brew uninstall thepixelabs/tap/rover
```

### pipx

```bash
pipx uninstall rover-tui
```

### uv

```bash
uv tool uninstall rover-tui
```

## Quick start

After install, on the host that runs your agents:

```bash
rover
```

Pick a project, pick an altergo account, and tmux takes over. From a phone, SSH to the same
host first:

```bash
ssh you@your-mac.local
```

Run `rover` — press `?` for the keymap.

## Keymap

### Main menu

| Key | Action |
|---|---|
| `↑` / `↓` / `j` / `k` | Move cursor |
| `1`–`9` | Jump to session N |
| `Enter` | Attach to the selected session |
| `Y` | Open the yolo submenu |
| `D` | Dispatch agent dashboard |
| `A` | altergo launcher (project + account picker) |
| `B` | Server / backend panel |
| `X` | Kill the selected tmux session (asks to confirm) |
| `S` | Settings |
| `Q` | Quit |

### Yolo submenu (`Y` from main menu)

| Key | Action |
|---|---|
| `y` | yolo-new — pick project + account, launch with `--yolo` |
| `r` | yolo-resume-last — resume the last session with `--yolo-resume` |
| `p` | yolo-pick — cross-account session picker, launch with `--yolo-resume <id>` |
| `Esc` / `q` | Cancel |

## Contributing

Issues and pull requests welcome at https://github.com/thepixelabs/rover.

## License

See [LICENSE](LICENSE).
