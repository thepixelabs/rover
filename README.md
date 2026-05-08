# Rover

The Dispatch TUI — SSH into your Mac from your phone and check, launch, or kill any agent.

## What Rover is

Rover is a terminal companion for Dispatch. It runs on your Mac (or a Linux host), and you reach
it over SSH from a phone or tablet to see which agents are running, start new ones, and kill the
ones that aren't.

## Prerequisites

- macOS or Linux (no Windows — use WSL)
- Python 3.11+
- tmux

## Install

### Homebrew (macOS one-liner)

```bash
brew install thepixelabs/tap/rover
```

### pipx (any Linux box with Python)

```bash
pipx install rover
```

### uv (modern pip alternative)

```bash
uv tool install rover
```

### Script (no-trust escape hatch)

```bash
curl -LsSf https://rover.thepixelabs.dev/install.sh | bash
```

## Update

### Homebrew

```bash
brew upgrade thepixelabs/tap/rover
```

### pipx

```bash
pipx upgrade rover
```

### uv

```bash
uv tool upgrade rover
```

### Script

```bash
curl -LsSf https://rover.thepixelabs.dev/install.sh | bash
```

## Uninstall

### Homebrew

```bash
brew uninstall thepixelabs/tap/rover
```

### pipx

```bash
pipx uninstall rover
```

### uv

```bash
uv tool uninstall rover
```

### Script

```bash
rm -rf ~/.rover ~/.local/bin/rover  # also remove the "rover auto-launch" block from ~/.zshrc
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

If you installed via the script channel, the auto-launch snippet runs `rover` for you on every
SSH connection. Otherwise, run `rover` once you're in.

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

The four teaser chords from the marketing site are `Y` (yolo), `D` (dashboard), `A` (altergo),
and `Q` (quit). Everything else is above.

## Escape hatch — what `install.sh` does

The script channel is the fallback for SSH hosts without Homebrew or pipx. On a clean run it:

- Creates a dedicated venv at `~/.rover` and installs Rover into it.
- Writes a launcher at `~/.local/bin/rover` that shells into that venv.
- Appends `export PATH="$HOME/.local/bin:$PATH"` to `~/.zshrc` if it isn't already there.
- Appends a `# rover auto-launch` block to `~/.zshrc` (after a `[Y/n]` prompt) so `rover` starts
  on every SSH login.
- Appends a `# Rover detach shortcut` block to `~/.tmux.conf` (Ctrl+Q to detach, prefix Ctrl+A).

To remove everything the script added, use the Script row in the Uninstall section above and
delete the `rover auto-launch` and `Rover detach shortcut` blocks from `~/.zshrc` and
`~/.tmux.conf`.
