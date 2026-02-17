# CLI Switcher

> Unified multi-account manager for **Gemini CLI** and **Codex CLI** — Ubuntu/Linux-first.

Switch between multiple Google Gemini and OpenAI Codex accounts instantly, without logging in again. Supports OAuth and API key profiles, keyring integration, health checks, and optional auto-rotation on quota exhaustion.

---

## Features

- **Instant profile switching** — symlink-based, no CLI restart for API key profiles
- **Both CLIs** — manages Gemini CLI and Codex CLI from one tool
- **OAuth + API key** — supports all auth types for both CLIs
- **Keyring integration** — writes to GNOME Keyring / KWallet (file fallback for headless)
- **Health checks** — validate tokens before switching
- **Auto-rotation** — Gemini hooks detect quota errors and switch profiles automatically
- **Shell integration** — `env.sh` sourced per invocation, aliases, wrappers
- **XDG compliant** — config in `~/.config/cli-switcher/`

## Requirements

- Python 3.10+
- Linux (Ubuntu 22.04+ recommended)
- [Gemini CLI](https://github.com/google-gemini/gemini-cli) and/or [Codex CLI](https://github.com/openai/codex)

## Installation

```bash
# Clone
git clone https://github.com/your-user/gemini-switcher.git
cd gemini-switcher

# Create venv and install
python3 -m venv .venv
source .venv/bin/activate
pip install -e .

# Install shell integration, hooks, and bin symlink
python main.py install
```

After installation, restart your shell or run `source ~/.bashrc` (or `~/.zshrc`).

## Quick Start

```bash
# Add a Gemini OAuth profile (import from existing login)
switcher gemini import ~/.gemini/oauth_creds.json work@gmail.com

# Add a second Gemini profile
switcher gemini import ~/backup/oauth_creds.json personal@gmail.com

# List profiles
switcher gemini list

# Switch to a profile by number or label
switcher gemini switch 2
switcher gemini switch personal@gmail.com

# Rotate to next profile
switcher gemini next

# Check health of all profiles
switcher gemini health

# Export a profile to back it up
switcher gemini export work@gmail.com ~/backups/
switcher gemini export 1 ~/backups/my-creds.json

# View status dashboard
switcher
```

### Codex CLI

```bash
# Add an API key profile
switcher codex add work-key --type apikey
# Then add your key to the file shown in the output

# Or import an existing auth.json
switcher codex import ~/.codex/auth.json my-chatgpt

# Switch
switcher codex switch work-key

# Export
switcher codex export work-key ~/backups/
```

## Command Reference

| Command | Description |
|---|---|
| `switcher` / `switcher status` | Show status dashboard |
| `switcher gemini list` | List Gemini profiles |
| `switcher gemini switch <n\|label>` | Switch to profile |
| `switcher gemini next` | Rotate to next profile |
| `switcher gemini add [label] [--type oauth\|apikey]` | Add profile |
| `switcher gemini remove <n\|label>` | Remove profile |
| `switcher gemini import <path> [label]` | Import credentials file |
| `switcher gemini export <n\|label> [dest]` | Export profile credentials |
| `switcher gemini health` | Check all profiles health |
| `switcher codex list` | List Codex profiles |
| `switcher codex switch <n\|label>` | Switch to profile |
| `switcher codex next` | Rotate to next |
| `switcher codex add [label] [--type apikey\|chatgpt]` | Add profile |
| `switcher codex remove <n\|label>` | Remove profile |
| `switcher codex import <path> [label]` | Import auth.json or API key |
| `switcher codex export <n\|label> [dest]` | Export profile credentials |
| `switcher config` | Show configuration |
| `switcher config set <key> <value>` | Set config value |
| `switcher install` | Install shell + hook integration |
| `switcher uninstall` | Remove integration |
| `switcher version` | Print version |

## How Switching Works

### Gemini (OAuth)
1. Backs up current credentials
2. Symlinks target profile's `oauth_creds.json` → `~/.gemini/oauth_creds.json`
3. Writes to keyring (`gemini-cli-oauth` service)
4. Clears MCP token cache

### Gemini (API key)
1. Writes `GEMINI_API_KEY` to `env.sh`
2. Shell wrapper sources `env.sh` before each `gemini` invocation
3. No restart needed

### Codex (API key)
1. Symlinks `auth.json` → `~/.codex/auth.json`
2. Writes `OPENAI_API_KEY` to `env.sh`

### Codex (ChatGPT OAuth)
1. Symlinks `auth.json` → `~/.codex/auth.json`
2. Codex reads tokens from file directly

## Auto-Rotation (Gemini)

When enabled, Gemini CLI hooks automatically detect quota errors and rotate to the next profile:

```bash
# Enable auto-rotation
switcher config set auto_rotate.enabled true

# Set max retries per session (default: 3)
switcher config set auto_rotate.max_retries 3

# Set quota threshold for proactive switching (default: 10%)
switcher config set auto_rotate.threshold 10
```

The **AfterAgent** hook detects "Resource exhausted" / "429" errors and triggers `switcher gemini next`. The **BeforeAgent** hook proactively checks quota via Google's API and switches before hitting limits.

## Configuration

Config stored in `~/.config/cli-switcher/config.toml`:

```toml
[general]
log_level = "info"

[auto_rotate]
enabled = false
max_retries = 3
threshold = 10
strategy = "conservative"  # or "gemini3-first"
cache_minutes = 5
pre_check = true
```

## Project Structure

```
switcher/
├── cli.py              # Argument parsing, command routing
├── config.py           # TOML config management
├── state.py            # Active profile state (JSON)
├── ui.py               # Terminal colors, tables, dashboard
├── utils.py            # XDG paths, logging, file locking
├── errors.py           # Exception hierarchy
├── health.py           # Token validation for all auth types
├── installer.py        # Shell RC, hooks, bin symlink
├── profiles/
│   ├── base.py         # Abstract ProfileManager
│   ├── gemini.py       # Gemini profile operations
│   └── codex.py        # Codex profile operations
├── auth/
│   ├── keyring_backend.py  # Keyring CRUD with fallback
│   ├── gemini_auth.py      # Gemini credential handling
│   └── codex_auth.py       # Codex credential handling
└── hooks/
    ├── gemini_after_agent.py   # Quota error detection
    └── gemini_before_agent.py  # Proactive quota check
```

## Development

```bash
source .venv/bin/activate

# Lint
ruff check switcher/
ruff format --check switcher/

# Run directly
python main.py status
python main.py gemini list
```

## License

MIT
