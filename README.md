# Rover

[![PyPI version](https://img.shields.io/pypi/v/rover-tui.svg)](https://pypi.org/project/rover-tui/)
[![GitHub release](https://img.shields.io/github/v/release/thepixelabs/rover)](https://github.com/thepixelabs/rover/releases)
[![License](https://img.shields.io/github/license/thepixelabs/rover)](LICENSE)
[![Tests](https://github.com/thepixelabs/rover/actions/workflows/ci.yml/badge.svg)](https://github.com/thepixelabs/rover/actions/workflows/ci.yml)

A terminal session manager — SSH in from your phone and manage tmux sessions and AI agents from anywhere.

Landing page: https://rover.pixelabs.net

## What Rover is

Rover is an SSH-friendly TUI session manager for your Mac. Check, launch, or kill any AI coding
agent from your phone in two keystrokes.

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

### Auto-launch on SSH (optional)

Add to your shell's startup file so every SSH login drops straight into rover.

**zsh** — `~/.zshrc`:

```bash
# auto-launch rover on SSH sessions
if [[ -n "$SSH_CONNECTION" ]] \
   && [[ -z "$TMUX" ]] \
   && [[ $- == *i* ]] \
   && command -v rover >/dev/null 2>&1; then
  exec rover
fi
```

**bash** — `~/.bash_profile` (macOS) or `~/.bashrc` (Linux):

```bash
# auto-launch rover on SSH sessions
if [[ -n "$SSH_CONNECTION" ]] \
   && [[ -z "$TMUX" ]] \
   && [[ $- == *i* ]] \
   && command -v rover >/dev/null 2>&1; then
  exec rover
fi
```

Guards: only fires over SSH, outside an existing tmux session, in interactive shells, and only when `rover` is on PATH.

## Keymap

### Main menu

| Key | Action |
|---|---|
| `↑` / `↓` / `j` / `k` | Move cursor |
| `1`–`9` | Jump to session N |
| `Enter` | Attach to the selected session |
| `Y` | Open the yolo submenu |
| `A` | altergo launcher (project + account picker) |
| `X` | Kill the selected tmux session (asks to confirm) |
| `R` | Resume a previous conversation (cross-account session picker) |
| `N` | New tmux session |
| `C` | Toggle keep-awake / caffeinate (macOS only) |
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

## Getting home — SSH connectivity

Need to establish an SSH path back to your Mac first? See [docs/ssh-setup.md](docs/ssh-setup.md) — covers Tailscale, router VPN (WireGuard / OpenVPN / IKEv2), and port forwarding with DDNS.

