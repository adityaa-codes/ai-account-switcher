<div align="center">

# AI Account Switcher

**Unified multi-account manager for [Gemini CLI](https://github.com/google-gemini/gemini-cli) and [Codex CLI](https://github.com/openai/codex) on Linux**

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Status: Alpha](https://img.shields.io/badge/status-alpha-orange.svg)]()

</div>

---

Switch between multiple Google Gemini and OpenAI Codex accounts instantly — no re-login required. AI Account Switcher manages OAuth tokens, API keys, keyring credentials, and shell wrappers so you can jump between work, personal, and test accounts in a single command.

## Table of Contents

- [Features](#features)
- [Requirements](#requirements)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [How-To Guides](#how-to-guides)
  - [Managing Gemini Profiles](#managing-gemini-profiles)
  - [Managing Codex Profiles](#managing-codex-profiles)
  - [Import & Export Profiles](#import--export-profiles)
  - [Cross-Machine Profile Transfer](#cross-machine-profile-transfer)
  - [Auto-Rotation (Gemini)](#auto-rotation-gemini)
  - [Live Quota Display](#live-quota-display)
  - [Interactive Menu](#interactive-menu)
  - [Health Checks](#health-checks)
  - [Pool Management](#pool-management)
  - [Alerts and Diagnostics](#alerts-and-diagnostics)
  - [Configuration](#configuration)
- [Command Reference](#command-reference)
- [How Switching Works](#how-switching-works)
- [Project Structure](#project-structure)
- [Contributing](#contributing)
- [License](#license)

---

## Features

- **Instant profile switching** — atomic symlink swaps, no CLI restart for API key profiles
- **Both CLIs, one tool** — manages Gemini CLI and Codex CLI from a single interface
- **All auth types** — OAuth, API keys (Gemini), API keys, ChatGPT OAuth (Codex)
- **Keyring integration** — writes to GNOME Keyring / KWallet with automatic file fallback for headless systems
- **Health checks** — validate tokens and API keys before switching
- **Live quota display** — `switcher gemini quota` shows quota used per OAuth profile with visual progress bars
- **Auto-rotation** — Gemini hooks detect quota exhaustion and rotate profiles automatically; hooks safely handle Gemini CLI's `stopHookActive` flag to prevent deadlocks
- **Codex isolation** — per-profile memory, plugin list, and sandbox policy snapshots restore automatically on switch
- **OAuth client caching** — discovered OAuth credentials are cached for 24 hours, reducing startup latency
- **Interactive menu** — `switcher gemini menu` launches a numbered TUI for profile management without memorising commands
- **Shell integration** — `env.sh` sourced per invocation via shell wrappers and aliases for bash, zsh, and fish
- **Import/export** — move profiles between machines or back them up
- **Pool sub-commands** — `switcher gemini pool health/export/status` for managing the rotation pool
- **Alerts** — `switcher alerts` tails recent error-log entries for quick diagnostics
- **Update check** — `switcher version --check` checks PyPI for a newer release
- **Discrete logging** — separate `errors.log` for error-only entries and `commands.log` for per-invocation timing
- **XDG compliant** — all state stored under `~/.config/ai-account-switcher/`

## Requirements

| Requirement | Details |
|---|---|
| **Python** | 3.10 or newer |
| **OS** | Linux (Ubuntu 22.04+ recommended) |
| **CLI tools** | [Gemini CLI](https://github.com/google-gemini/gemini-cli) and/or [Codex CLI](https://github.com/openai/codex) |
| **Optional** | GNOME Keyring or KWallet for secure credential storage |

## Compatibility Matrix and Upstream Assumptions

`ai-account-switcher` tracks upstream CLI internals that can change between releases.
The versions below are the ones currently validated by this project.

| Component | Validated versions | Notes |
|---|---|---|
| Gemini CLI | `0.33.x` to `0.34.0-nightly` | OAuth client discovery supports multiple `gemini-cli-core/dist/` layouts and caches discovered credentials for 24h. |
| Codex CLI | `0.113.0` | `auth.json` detection supports legacy nested `tokens` and newer flat `api_key` / `access_token` layouts. |

Current compatibility assumptions:

- Gemini OAuth client constants may move between `dist/src/code_assist/oauth2.js`, `dist/src/auth/oauth2.js`, and `dist/src/oauth.js`.
- Gemini quota checks rely on undocumented internal endpoints (`loadCodeAssist`, `retrieveUserQuota`); failures degrade gracefully without breaking profile switching.
- Codex OAuth validation is refresh-token based when available; access-token-only formats are reported as `unknown` (not `expired`) to avoid false negatives.
- Codex auth-mode detection treats either `OPENAI_API_KEY` or `api_key` as API-key mode.

### Upstream Release Verification Checklist

When Gemini CLI or Codex CLI ships a new release, run this checklist before declaring support:

1. Run `switcher gemini health` and verify OAuth refresh still succeeds.
2. Run `switcher gemini quota` and verify tier/reset parsing still works.
3. Run `switcher codex health` against both API-key and ChatGPT profiles.
4. Import representative auth files (`switcher codex import ...`) for both nested and flat `auth.json` layouts.
5. Run `./.venv/bin/pytest` and ensure compatibility tests remain green.

Diagnostics:

- `switcher doctor` checks for stale API-key exports and broken auth symlinks.
- `switcher fix` clears common OAuth-mode conflicts and repairs known auth pointers.

## Installation

### From Source (recommended)

```bash
# 1. Clone the repository
git clone https://github.com/your-user/ai-account-switcher.git
cd ai-account-switcher

# 2. Install from PyPI
pip install ai-account-switcher

# --- OR install from source (development) ---
python3 -m venv .venv
source .venv/bin/activate
pip install -e .

# 3. Install shell integration, hooks, and the `switcher` bin symlink
switcher install

# 4. Reload your shell
source ~/.bashrc         # bash
source ~/.zshrc          # zsh
source ~/.config/fish/config.fish   # fish
```

`switcher install` writes shell-specific integration to:
- `~/.bashrc` for bash
- `~/.zshrc` for zsh
- `~/.config/fish/config.fish` for fish

### Verify Installation

```bash
switcher version
# ai-account-switcher 0.3.0

switcher
# Shows the status dashboard
```

### Uninstall

```bash
switcher uninstall   # removes shell hooks, aliases, bin symlink
pip uninstall ai-account-switcher
```

## Quick Start

```bash
# One-time shell integration
switcher install

# Plug-and-play: adopt existing Gemini/Codex logins automatically
switcher setup

# Re-scan and adopt later (idempotent)
switcher discover

# Daily usage: pick best available profile automatically
switcher use gemini
switcher use codex

# Diagnose and repair common auth conflicts
switcher doctor
switcher fix

# Optional: inspect current state
switcher
```

---

## How-To Guides

### Managing Gemini Profiles

#### Add a new OAuth profile (interactive login)

```bash
switcher gemini add my-account --type oauth
# Follow the OAuth flow in your browser, then import the generated credentials
```

#### Add an API key profile

```bash
switcher gemini add my-api-key --type apikey
# The command creates a profile directory — add your API key to the file shown in output
```

#### Switch between profiles

```bash
# By label
switcher gemini switch work

# By index number (shown in `list`)
switcher gemini switch 2

# Rotate to the next profile in order
switcher gemini next

# /change command — no target rotates, label/number switches directly
switcher gemini change
switcher gemini change personal
switcher gemini change 2
```

#### Remove a profile

```bash
switcher gemini remove personal
switcher gemini remove 3
```

### Managing Codex Profiles

#### Add an API key profile

```bash
switcher codex add work-key --type apikey
# Add your OPENAI_API_KEY to the file shown in output
```

#### Import an existing auth.json

```bash
switcher codex import ~/.codex/auth.json my-chatgpt
```

#### Switch and rotate

```bash
switcher codex switch work-key
switcher codex next
```

#### Codex profile isolation

When switching Codex profiles, the following are automatically snapshotted and restored:

- **Conversation memory** — Codex's SQLite/flat-file memory store is saved per profile
- **Plugin list** — diverging plugins between profiles are reported as a warning
- **Sandbox policy** — `policy.toml` is saved per profile and restored on switch

### Import & Export Profiles

#### Export a profile to a file

```bash
# Export by label — writes to current directory
switcher gemini export work

# Export to a specific path
switcher gemini export work ~/backups/gemini-work.json

# Export by index number
switcher gemini export 1 ~/backups/
```

#### Import a profile from a file

```bash
# Import with a custom label
switcher gemini import /path/to/oauth_creds.json work-account

# Import with auto-detected label
switcher codex import /path/to/auth.json
```

The importer auto-detects the auth type (OAuth vs API key) from the file contents.

### Cross-Machine Profile Transfer

You can export profiles on one machine and import them on another:

```bash
# ── Machine A ──
switcher gemini export work /tmp/work-creds.json

# Transfer the file securely (scp, USB, etc.)
scp /tmp/work-creds.json user@machine-b:/tmp/

# ── Machine B ──
switcher gemini import /tmp/work-creds.json work
```

**What transfers:**
- ✅ OAuth credentials (`oauth_creds.json` with refresh tokens)
- ✅ API keys (`api_key.txt` or `auth.json`)

**What does NOT transfer:**
- ❌ Profile metadata (label, notes, health status — regenerated on import)
- ❌ Keyring entries (re-created automatically on first switch)

**Security notes:**
- Exported files contain **plaintext credentials** — transfer securely and delete intermediate files
- OAuth refresh tokens may expire or be device-bound; re-authenticate if needed after import

### Auto-Rotation (Gemini)

Auto-rotation uses Gemini CLI's hook system to detect quota exhaustion and automatically switch to the next available profile.

#### Enable auto-rotation

```bash
switcher config set auto_rotate.enabled true
```

#### Configure rotation behavior

```bash
# Maximum retry attempts per session (default: 3)
switcher config set auto_rotate.max_retries 3

# Quota threshold percentage for proactive switching (default: 10)
switcher config set auto_rotate.threshold 10

# Rotation strategy: "conservative" (default) or "gemini3-first"
switcher config set auto_rotate.strategy conservative

# Cache quota check results for N minutes (default: 5)
switcher config set auto_rotate.cache_minutes 5

# Enable proactive pre-check before each request (default: true)
switcher config set auto_rotate.pre_check true

# After rotating, instruct Gemini CLI to restart the agent (default: false)
switcher config set auto_rotate.restart_on_switch true
```

#### How it works

1. **AfterAgent hook** — runs after each Gemini CLI response. Detects "Resource exhausted" / HTTP 429 errors and triggers `switcher gemini next`. After rotating, writes a short-lived handoff flag so the next hook invocation skips its API call. Safely exits with `{}` when `stopHookActive` is set.
2. **BeforeAgent hook** — runs before each request. Checks for the handoff flag first (skipping the API call if set); otherwise proactively checks remaining quota via Google's API and switches profiles before hitting limits. Safely exits with `{}` when `stopHookActive` is set.

Hooks are registered in `~/.gemini/settings.json` by `switcher install`. Re-running `switcher install` is safe — hooks are updated in-place without duplicates.

### Live Quota Display

View real-time quota usage for all Gemini OAuth profiles:

```bash
switcher gemini quota
```

Sample output:

```
ℹ️  Fetching quota for 2 OAuth profile(s)...

  ──────────────────────────────────────────────────────────────

  work ●
  (you@work.com)  [Tier: Standard]
    gemini-2.0-flash          ██░░░░░░░░░░░░  14.7% used

  personal
  (you@personal.com)
    gemini-2.0-flash          ████████████░░  87.9% used ⚠️  resets in 4 h
```

- `●` marks the active profile
- `⚠️` appears when quota used exceeds 80%
- Tier name is shown when available from the API
- Only OAuth profiles are checked (API key profiles have no quota API)

### Interactive Menu

Launch a numbered TUI for profile management — useful when you don't remember the exact command:

```bash
switcher gemini menu
# or
switcher codex menu
```

```
  Gemini Profile Manager
  Active: work
  ────────────────────────────────────
   1)  List all profiles
   2)  Switch to a profile
   3)  Rotate to next profile
   4)  Show live quota usage
   5)  Check profile health
   6)  Add a new profile
   7)  Import credentials
   8)  Toggle auto-rotate on/off
   q)  Quit

  Choice:
```

When stdin is not a TTY (e.g. piped or in a script), the menu prints a compact command reference instead of prompting.

### Slash Commands

`switcher install` configures the following CLI-native slash commands:

- **Gemini CLI**
  - `/change` → alias for `switcher gemini change` — no argument rotates to next profile, a label or number switches directly
  - Command file: `~/.gemini/commands/change.toml`
- **Codex CLI**
  - No custom slash commands are installed by `ai-account-switcher` currently.
  - Use regular commands instead (for example: `sw codex next`).

### Health Checks

Validate that your profiles' credentials are still working:

```bash
# Check all Gemini profiles
switcher gemini health

# Check all Codex profiles
switcher codex health
```

Health checks verify:
- **OAuth tokens** — test refresh token validity against the provider's token endpoint
- **API keys** — make a lightweight API call to confirm the key is active
- **Status values** — `healthy`, `expired`, `invalid`, `rate_limited`, `unknown`

### Troubleshooting Quick Fixes

| Symptom | Likely cause | One-line fix |
|---|---|---|
| Stuck on Gemini sign-in screen | Non-interactive OAuth launch or stale auth mode | `NO_BROWSER=true gemini` |
| Gemini OAuth consent failed | Browser flow failed in current terminal session | `switcher doctor && switcher fix` |
| Codex keeps using API key instead of OAuth | Stale `OPENAI_API_KEY` export overrides file auth | `switcher fix` |
| Already logged in but profile not visible in switcher | Credentials not adopted yet | `switcher discover` |
| Fresh machine setup confusion | Shell integration/adopt flow not run yet | `switcher setup` |

### Acceptance Smoke Check

Run the local acceptance script to verify three paths quickly:
- adopt existing login state (`discover`)
- fresh setup guidance (`setup --fresh --no-install`)
- diagnostics/remediation (`doctor` and `fix`)

```bash
bash scripts/acceptance-smoke.sh
```

### Pool Management

The `pool` sub-commands offer a focused view of the rotation pool:

```bash
# List all pool profiles
switcher gemini pool list

# Run health checks across all pool profiles
switcher gemini pool health

# Export all pool profiles to a directory
switcher gemini pool export --dest ~/backups/gemini-pool/

# Show rotation state and next-up profile
switcher gemini pool status
```

### Alerts and Diagnostics

```bash
# Tail the last 20 error-log entries (default)
switcher alerts

# Show more lines
switcher alerts --lines 50

# Check for a newer release on PyPI
switcher version --check
```

Discrete log files:

| File | Contents |
|---|---|
| `~/.config/ai-account-switcher/logs/switcher.log` | Full application log (all levels) |
| `~/.config/ai-account-switcher/logs/errors.log` | Error-only entries for quick triage |
| `~/.config/ai-account-switcher/logs/commands.log` | Per-invocation timing and exit status |

### Configuration

All configuration is stored in `~/.config/ai-account-switcher/config.toml`:

```toml
[general]
log_level = "info"          # debug, info, warning, error

[auto_rotate]
enabled = false
max_retries = 3
threshold = 10
strategy = "conservative"   # or "gemini3-first"
cache_minutes = 5
pre_check = true
restart_on_switch = false   # ask Gemini CLI to restart agent after rotation
```

#### View and modify config

```bash
# Show all configuration
switcher config

# Get a specific value
switcher config get general.log_level

# Set a value
switcher config set general.log_level debug
```

---

## Command Reference

### Global Commands

| Command | Description |
|---|---|
| `switcher` or `switcher status` | Show status dashboard for all CLIs |
| `switcher config` | Show current configuration |
| `switcher config set <key> <value>` | Set a config value |
| `switcher install` | Install shell integration, hooks, and bin symlink |
| `switcher uninstall` | Remove all integration |
| `switcher setup [--adopt\|--fresh] [--no-install]` | Guided setup; adopts existing CLI auth by default |
| `switcher discover` | Re-scan and adopt existing Gemini/Codex credentials |
| `switcher use <gemini\|codex>` | Activate active valid profile or healthiest available one |
| `switcher doctor` | Diagnose auth env/symlink conflicts |
| `switcher fix` | Repair common auth conflicts (env exports, symlinks, Gemini cache) |
| `switcher alerts [--lines N]` | Tail recent error-log entries |
| `switcher version` | Print version |
| `switcher version --check` | Print version and check PyPI for updates |

### Gemini Commands

| Command | Description |
|---|---|
| `switcher gemini list` | List all Gemini profiles with status |
| `switcher gemini switch <n\|label>` | Switch to a profile by index or label |
| `switcher gemini next` | Rotate to the next profile |
| `switcher gemini change [n\|label]` | Slash-command parity: no arg → next, label/index → switch |
| `switcher gemini menu` | Launch interactive profile management menu |
| `switcher gemini quota` | Show live quota usage (% used) for all OAuth profiles |
| `switcher gemini add [label] [--type oauth\|apikey]` | Create a new empty profile |
| `switcher gemini remove <n\|label>` | Delete a profile |
| `switcher gemini import <path> [label]` | Import credentials from a file |
| `switcher gemini export <n\|label> [dest]` | Export profile credentials to a file |
| `switcher gemini health` | Run health checks on all profiles |
| `switcher gemini pool` | Alias for `list` |
| `switcher gemini pool list` | List rotation pool profiles |
| `switcher gemini pool health` | Run health checks across pool profiles |
| `switcher gemini pool export [--dest DIR]` | Export all pool profiles to a directory |
| `switcher gemini pool status` | Show rotation state and next-up profile |
| `switcher gemini pool add [label]` | Alias for `add` |
| `switcher gemini pool remove <n\|label>` | Alias for `remove` |
| `switcher gemini pool import <path> [label]` | Alias for `import` |

### Codex Commands

| Command | Description |
|---|---|
| `switcher codex list` | List all Codex profiles with status |
| `switcher codex switch <n\|label>` | Switch to a profile by index or label |
| `switcher codex next` | Rotate to the next profile |
| `switcher codex change [n\|label]` | Slash-command parity: no arg → next, label/index → switch |
| `switcher codex menu` | Launch interactive profile management menu |
| `switcher codex add [label] [--type apikey\|chatgpt]` | Create a new empty profile |
| `switcher codex remove <n\|label>` | Delete a profile |
| `switcher codex import <path> [label]` | Import auth.json or API key file |
| `switcher codex export <n\|label> [dest]` | Export profile credentials to a file |
| `switcher codex pool` | Alias for `list` |
| `switcher codex pool list` | List rotation pool profiles |
| `switcher codex pool health` | Run health checks across pool profiles |
| `switcher codex pool export [--dest DIR]` | Export all pool profiles to a directory |
| `switcher codex pool status` | Show rotation state and next-up profile |
| `switcher codex pool add [label]` | Alias for `add` |
| `switcher codex pool remove <n\|label>` | Alias for `remove` |
| `switcher codex pool import <path> [label]` | Alias for `import` |

---

## How Switching Works

### Gemini — OAuth Profiles
1. Creates an atomic symlink: `~/.gemini/oauth_creds.json` → profile directory
2. Writes credentials to the OS keyring (service: `gemini-cli-oauth`, key: `main-account`)
3. Deletes `~/.gemini/mcp-oauth-tokens.json` (token cache) to avoid stale sessions
4. Removes stale `GEMINI_API_KEY` and `GOOGLE_API_KEY` exports for Gemini from `env.sh`
5. Next Gemini CLI invocation picks up the new credentials immediately

### Gemini — API Key Profiles
1. Writes `GEMINI_API_KEY` and `GOOGLE_API_KEY` to `~/.config/ai-account-switcher/env.sh`
2. Shell wrapper sources `env.sh` before launching `gemini`
3. No restart needed — takes effect on next invocation

### Codex — API Key Profiles
1. Creates an atomic symlink: `~/.codex/auth.json` → profile directory
2. Snapshots/restores per-profile memory (SQLite DB), plugin list, and sandbox policy
3. Writes `OPENAI_API_KEY` to `env.sh`
4. Shell wrapper sources `env.sh` before launching `codex`

### Codex — ChatGPT OAuth Profiles
1. Creates an atomic symlink: `~/.codex/auth.json` → profile directory
2. Removes stale `OPENAI_API_KEY` exports for Codex from `env.sh`
3. Codex CLI reads tokens from the file directly
4. May require a Codex restart for ChatGPT OAuth (account-ID-gated `reload()`)

### Auth Env Precedence
- `GEMINI_API_KEY` and `GOOGLE_API_KEY` take precedence over Gemini file-based auth when exported.
- `OPENAI_API_KEY` takes precedence over Codex API-key file state when exported.
- Switching a CLI from API key to OAuth clears that CLI's env exports to avoid stale auth-mode leaks.
- Switching one CLI preserves the other CLI's exported API key in `env.sh`.

---

## Project Structure

```
ai-account-switcher/
├── main.py                 # Direct-run entry point
├── pyproject.toml           # Project metadata and dependencies
├── docs/
│   └── spec.md             # Full technical specification
├── switcher/
│   ├── __init__.py
│   ├── cli.py              # Argument parsing, command routing
│   ├── config.py           # TOML config management
│   ├── state.py            # Active profile state + OAuth client cache + handoff flags
│   ├── ui.py               # Terminal colors, tables, dashboard
│   ├── ui_menu.py          # Interactive numbered TUI menu
│   ├── utils.py            # XDG paths, logging, file locking, atomic symlinks
│   ├── errors.py           # Custom exception hierarchy
│   ├── health.py           # Token/key validation, quota fetch, OAuth client discovery
│   ├── installer.py        # Shell RC injection, hooks, bin symlinks, env.sh generation
│   ├── profiles/
│   │   ├── base.py         # Abstract ProfileManager
│   │   ├── gemini.py       # Gemini profile operations
│   │   └── codex.py        # Codex profile operations + isolation integration
│   ├── auth/
│   │   ├── keyring_backend.py  # Keyring CRUD with file fallback
│   │   ├── gemini_auth.py      # Gemini credential activation
│   │   ├── codex_auth.py       # Codex credential activation
│   │   ├── codex_memory.py     # Per-profile Codex memory snapshot/restore
│   │   ├── codex_plugins.py    # Per-profile plugin list snapshot + divergence warning
│   │   └── codex_sandbox.py    # Per-profile sandbox policy snapshot/restore
│   └── hooks/
│       ├── quota_patterns.py       # Centralised quota-error regex patterns
│       ├── gemini_after_agent.py   # Post-response quota error detection + rotation
│       └── gemini_before_agent.py  # Pre-request proactive quota check
└── tests/                  # Test suite (pytest, 471+ tests)
```

### Key File Paths

| Path | Purpose |
|---|---|
| `~/.config/ai-account-switcher/config.toml` | User preferences |
| `~/.config/ai-account-switcher/state.json` | Active profiles, rotation state |
| `~/.config/ai-account-switcher/state/quota_error_gemini.json` | Short-lived handoff flag (AfterAgent → BeforeAgent) |
| `~/.config/ai-account-switcher/env.sh` | Exported API key environment variables |
| `~/.config/ai-account-switcher/cache/oauth_client.json` | Cached OAuth client credentials (24-hour TTL) |
| `~/.config/ai-account-switcher/profiles/` | Profile credential storage |
| `~/.config/ai-account-switcher/logs/switcher.log` | Full application log |
| `~/.config/ai-account-switcher/logs/errors.log` | Error-only log for quick triage |
| `~/.config/ai-account-switcher/logs/commands.log` | Per-command timing and exit status |
| `~/.gemini/oauth_creds.json` | Symlinked by switcher |
| `~/.gemini/settings.json` | Gemini hooks registered here |
| `~/.codex/auth.json` | Symlinked by switcher |

---

## Contributing

Contributions are welcome! Here's how to get started.

### Setting Up the Development Environment

```bash
# Clone and enter the repository
git clone https://github.com/your-user/ai-account-switcher.git
cd ai-account-switcher

# Create a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install in editable mode with dev dependencies
pip install -e ".[dev]"
```

### Running Tests

```bash
# Run the full test suite
pytest

# Run a specific test file
pytest tests/test_config.py -v

# Run with coverage
pytest --cov=switcher --cov-report=term-missing
```

### Linting and Formatting

```bash
# Check for lint issues
ruff check switcher/ tests/

# Auto-fix lint issues
ruff check --fix switcher/ tests/

# Check formatting
ruff format --check switcher/ tests/

# Auto-format
ruff format switcher/ tests/
```

### Type Checking

```bash
mypy switcher/
```

### Code Style Guidelines

- **Python 3.10+** — use `from __future__ import annotations` for modern union syntax
- **Ruff** for linting and formatting (line-length 88; rules: E, F, W, I, B, UP, RUF, SIM, TCH)
- **mypy --strict** for type checking
- `pathlib.Path` for all filesystem paths — never raw strings
- `dataclasses.dataclass(slots=True)` for structured data
- Google-style docstrings (`Args:`, `Returns:`, `Raises:`)
- `argparse` for CLI — no third-party CLI frameworks

### Testing Conventions

- **Never** touch real `~/.gemini/`, `~/.codex/`, or the OS keyring in tests
- Use `tmp_path` fixtures and `mock_keyring` for isolation
- Patch `switcher.utils.get_config_dir()` / `get_gemini_dir()` / `get_codex_dir()` to return temp paths
- Mock HTTP calls (`requests.post` / `requests.get`) for health checks and quota APIs
- Target: **≥80% line coverage**

### Submitting Changes

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/my-feature`
3. Make your changes with clear, atomic commits
4. Ensure all checks pass: `ruff check && ruff format --check && mypy switcher/ && pytest`
5. Push and open a pull request against `main`

### Reporting Issues

- Use GitHub Issues to report bugs or request features
- Include your Python version, OS, and the output of `switcher version`
- For bugs, run `switcher alerts` or check `~/.config/ai-account-switcher/logs/errors.log`

---

## License

This project is licensed under the **MIT License** — see the [LICENSE](LICENSE) file for details.
