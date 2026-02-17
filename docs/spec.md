# CLI Switcher — Technical Specification

> **Unified multi-account manager for Gemini CLI and Codex CLI on Ubuntu/Linux.**
>
> Version: 0.1.0-draft
> Target: Python 3.10+, Ubuntu 22.04+

---

## Table of Contents

1. [Overview](#1-overview)
2. [Goals & Non-Goals](#2-goals--non-goals)
3. [Gap Analysis — Besty0728 Tool](#3-gap-analysis--besty0728-tool)
4. [Architecture](#4-architecture)
5. [Data Model](#5-data-model)
6. [Auth Mechanics Deep Dive](#6-auth-mechanics-deep-dive)
7. [CLI Interface](#7-cli-interface)
8. [Hook System](#8-hook-system)
9. [Shell Integration](#9-shell-integration)
10. [Health Check System](#10-health-check-system)
11. [Error Handling & Logging](#11-error-handling--logging)
12. [Dependencies](#12-dependencies)
13. [Source File Map](#13-source-file-map)
14. [Detailed Task List](#14-detailed-task-list)
15. [Open Questions & Risks](#15-open-questions--risks)
16. [Python Coding Standards](#16-python-coding-standards-researched-feb-2026)
17. [Additional Codebase Findings](#17-additional-codebase-findings-deep-dive-feb-2026)

---

## 1. Overview

`switcher` is a single Python CLI tool that manages multiple authentication
profiles for **Google Gemini CLI** and **OpenAI Codex CLI**. It supports:

- Instant manual switching between accounts
- Optional automatic rotation on quota exhaustion (Gemini only, via hooks)
- Linux keyring integration (GNOME Keyring / KWallet) with file fallback
- Both OAuth and API key auth modes for each CLI
- Shell wrappers that avoid the need to restart CLIs after switching

---

## 2. Goals & Non-Goals

### Goals

- Ubuntu/Linux-first design — all paths, integrations, and defaults target Linux
- Single tool for both Gemini and Codex account management
- Zero-restart switching for API key profiles via env-var shell wrappers
- Keyring-aware credential storage matching each CLI's native format
- Profile health checks (token validity, quota status)
- XDG Base Directory compliance (`~/.config/cli-switcher/`)
- Optional auto-rotation via Gemini CLI's hook system
- Minimal dependencies — no heavy frameworks

### Non-Goals

- Windows/macOS support (may work but not tested or prioritized)
- GUI or TUI (ncurses) — terminal text UI only
- Modifying Gemini CLI or Codex CLI source code
- Managing non-auth config (model preferences, system prompts, etc.)
- Multi-user / shared machine scenarios
- Auto-rotation for Codex CLI (no hook system available)

---

## 3. Gap Analysis — Besty0728 Tool

| # | Gap | Impact | Our Fix |
|---|-----|--------|---------|
| 1 | **Windows-only** — `.bat` launcher, `setx`, `taskkill`, `start /b` | Completely broken on Linux | Linux-native: symlinks, `.bashrc`, `kill` |
| 2 | **Ignores keychain migration** — Gemini CLI now uses `HybridTokenStorage` (OS keychain first) | Swapping `oauth_creds.json` has no effect when keyring is active | Write to both file AND keyring, matching `HybridTokenStorage` schema |
| 3 | **No Codex support** | Can't manage OpenAI accounts | Unified profile management for both CLIs |
| 4 | **Requires CLI restart** after every switch | Breaks workflow, loses context | Env-var shell wrappers for API keys; `systemMessage` hint for OAuth |
| 5 | **No token validation** | Switches to accounts with expired/revoked tokens | Health check system with token refresh validation |
| 6 | **Bare `except:` everywhere** | Silent failures, impossible to debug | Typed exceptions (`SwitcherError` hierarchy), structured logging |
| 7 | **Config read on every `t()` call** | Disk I/O on every string translation during rendering | In-memory config cache, reload on explicit command |
| 8 | **No XDG compliance** | Dumps files in `~/.gemini/` alongside CLI's own files | `~/.config/cli-switcher/` for all tool state |
| 9 | **File copy on switch** | Risk of data loss if interrupted mid-copy | Atomic symlink swap (`os.replace` on temp symlink) |
| 10 | **Hardcoded `platform: "WINDOWS_AMD64"`** | Wrong platform in API calls from Linux | Dynamic platform detection via `sys.platform` + `platform.machine()` |
| 11 | **`v1internal` API with no error handling** | Breaks silently when Google changes internal APIs | Graceful degradation — quota features are optional, core switching works without API |
| 12 | **Race condition on cache clear** | Running CLI recreates cache from memory before restart | Clear cache + write new creds atomically, then signal restart |
| 13 | **No file locking** | Concurrent hook invocations can corrupt `state.json` | `fcntl.flock` on state file writes |

---

## 4. Architecture

### 4.1 Directory Layout (Tool State)

```
$XDG_CONFIG_HOME/cli-switcher/           # defaults to ~/.config/cli-switcher/
├── config.toml                          # User preferences
├── state.json                           # Active profile per CLI, rotation state
├── profiles/
│   ├── gemini/
│   │   ├── <email>/
│   │   │   ├── oauth_creds.json         # Google OAuth credentials
│   │   │   ├── google_account_id        # Account identifier (optional)
│   │   │   └── meta.json               # Profile metadata
│   │   └── <label>/                     # API key profiles use a label
│   │       ├── api_key.txt              # Plaintext API key (file mode)
│   │       └── meta.json
│   └── codex/
│       ├── <label>/
│       │   ├── auth.json               # Codex auth file
│       │   └── meta.json
│       └── ...
├── hooks/
│   ├── gemini_after_agent.py           # AfterAgent hook script
│   └── gemini_before_agent.py          # BeforeAgent hook script
├── env.sh                              # Shell env vars for active API keys
└── logs/
    └── switcher.log                    # Rotating log file
```

### 4.2 Target CLI Directories (Modified by Switcher)

```
~/.gemini/
├── oauth_creds.json    → SYMLINK to active Gemini profile
├── settings.json       ← hooks injected here by `switcher install`
└── commands/
    └── change.toml     ← slash command installed here

~/.codex/
└── auth.json           → SYMLINK to active Codex profile
```

### 4.3 Source Code Layout

```
gemini-switcher/
├── main.py                          # Entry point
├── pyproject.toml                   # Project metadata + dependencies
├── README.md                        # User documentation
├── docs/
│   └── spec.md                      # This file
├── switcher/
│   ├── __init__.py                  # Package init, version
│   ├── cli.py                       # argparse CLI routing
│   ├── config.py                    # TOML config management
│   ├── state.py                     # Active profile state (JSON)
│   ├── ui.py                        # Terminal output (colors, tables)
│   ├── utils.py                     # Paths, platform, logging, file locking
│   ├── errors.py                    # Exception hierarchy
│   ├── profiles/
│   │   ├── __init__.py
│   │   ├── base.py                  # Abstract ProfileManager
│   │   ├── gemini.py                # Gemini profile operations
│   │   └── codex.py                 # Codex profile operations
│   ├── auth/
│   │   ├── __init__.py
│   │   ├── keyring_backend.py       # Keyring R/W with file fallback
│   │   ├── gemini_auth.py           # Gemini credential handler
│   │   └── codex_auth.py            # Codex credential handler
│   ├── hooks/
│   │   ├── __init__.py
│   │   ├── gemini_after_agent.py    # AfterAgent hook (runs standalone)
│   │   └── gemini_before_agent.py   # BeforeAgent hook (runs standalone)
│   ├── health.py                    # Token/key validation
│   └── installer.py                 # Shell + hook installer
└── tests/                           # Unit tests (future)
    ├── test_config.py
    ├── test_profiles.py
    └── test_auth.py
```

---

## 5. Data Model

### 5.1 `config.toml`

```toml
[general]
default_cli = "gemini"               # "gemini" | "codex"
storage_mode = "keyring"             # "keyring" | "file" | "auto"
log_level = "info"                   # "debug" | "info" | "warn" | "error"

[auto_rotate]
enabled = false                      # Manual by default
strategy = "gemini3-first"           # "conservative" | "gemini3-first"
model_pattern = "gemini-3.*"         # Regex for target models
threshold_percent = 10               # Switch when remaining < this %
max_retries = 3                      # Max consecutive switches before giving up
cache_minutes = 3                    # Quota cache TTL

[auto_rotate.codex]
enabled = false                      # Codex has no hooks — manual only
```

### 5.2 `state.json`

```json
{
  "gemini": {
    "active_profile": "work@gmail.com",
    "rotation_index": 0,
    "retry_count": 0,
    "last_switch": "2026-02-17T12:00:00Z",
    "last_error": null
  },
  "codex": {
    "active_profile": "work-apikey",
    "rotation_index": 0,
    "last_switch": "2026-02-17T12:00:00Z"
  }
}
```

### 5.3 `meta.json` (per profile)

```json
{
  "label": "work@gmail.com",
  "auth_type": "oauth",
  "added_at": "2026-02-17T12:00:00Z",
  "last_used": "2026-02-17T12:00:00Z",
  "last_health_check": "2026-02-17T12:00:00Z",
  "health_status": "valid",
  "health_detail": "Token refreshed successfully",
  "notes": "Work Google account — Pro tier"
}
```

`health_status` enum: `"valid"` | `"expiring"` | `"expired"` | `"revoked"` | `"unknown"`

### 5.4 `env.sh` (generated)

```bash
# Auto-generated by cli-switcher — do not edit manually
# Active Gemini API key (if API key profile is active)
export GEMINI_API_KEY="AIza..."

# Active Codex API key (if API key profile is active)
export OPENAI_API_KEY="sk-..."
```

---

## 6. Auth Mechanics Deep Dive

### 6.1 Gemini CLI — OAuth Flow

**How Gemini CLI stores credentials (current, from source):**

1. On first login, user goes through Google OAuth flow
2. Credentials stored via `OAuthCredentialStorage` → `HybridTokenStorage`
3. `HybridTokenStorage` tries OS keyring first (service: `gemini-cli-oauth`, key: `main-account`)
4. Falls back to `~/.gemini/oauth_creds.json` if keyring unavailable
5. On startup, CLI loads credentials from keyring/file into memory and caches them
6. Token refresh happens via `refresh_token` when `access_token` expires

**Keyring credential format** (JSON string stored in keyring):

```json
{
  "serverName": "main-account",
  "token": {
    "accessToken": "ya29.a0...",
    "refreshToken": "1//0d...",
    "tokenType": "Bearer",
    "scope": "openid email ...",
    "expiresAt": 1739800000000
  },
  "updatedAt": 1739796400000
}
```

**Our switch procedure for Gemini OAuth:**

```
1. Read current active profile from state.json
2. If current profile exists:
   a. Read current creds from ~/.gemini/oauth_creds.json (or keyring)
   b. Save back to profiles/gemini/<current>/oauth_creds.json
3. Create temp symlink: ~/.gemini/.oauth_creds.json.tmp → target profile creds
4. Atomic rename: mv ~/.gemini/.oauth_creds.json.tmp ~/.gemini/oauth_creds.json
5. If keyring mode:
   a. Delete keyring entry: service=gemini-cli-oauth, key=main-account
   b. Write new creds to keyring in HybridTokenStorage format
6. Delete ~/.gemini/mcp-oauth-tokens.json (token cache)
7. Update state.json with new active profile
8. Print success + "restart Gemini CLI to apply" hint (for OAuth)
```

### 6.2 Gemini CLI — API Key Flow

**How it works:** Gemini CLI reads `GEMINI_API_KEY` env var. If set, it uses
the API key directly — no OAuth, no keyring, no file.

**Our switch procedure for Gemini API Key:**

```
1. Read API key from profiles/gemini/<label>/api_key.txt
   (or from keyring: service=cli-switcher-gemini, key=<label>)
2. Write to env.sh: export GEMINI_API_KEY="<key>"
3. Update state.json
4. Print success — no restart needed (shell wrapper sources env.sh)
```

### 6.3 Codex CLI — API Key Flow

**How Codex stores credentials (from source):**

1. `auth.json` in `$CODEX_HOME` (defaults to `~/.codex/`)
2. Format: `{"OPENAI_API_KEY": "sk-...", "tokens": null, "last_refresh": null}`
3. Also reads `OPENAI_API_KEY` env var directly

**Our switch procedure for Codex API Key:**

```
1. Create temp symlink: ~/.codex/.auth.json.tmp → target profile auth.json
2. Atomic rename: mv ~/.codex/.auth.json.tmp ~/.codex/auth.json
3. Write to env.sh: export OPENAI_API_KEY="<key>"
4. Update state.json
5. Print success — no restart needed
```

### 6.4 Codex CLI — ChatGPT OAuth Flow

**How it works:**

1. User logs in via browser or device code flow
2. Credentials stored in `~/.codex/auth.json` as:
   ```json
   {
     "tokens": {
       "access_token": "eyJ...",
       "refresh_token": "v1:...",
       "expires_at": "2026-02-17T14:00:00Z",
       "chatgpt_account_id": "acct_..."
     }
   }
   ```
3. Token refresh via `https://auth.openai.com/oauth/token`
4. Optional: credentials stored in OS keyring via `AuthCredentialsStoreMode`

**Our switch procedure for Codex ChatGPT:**

```
1. Symlink target auth.json → ~/.codex/auth.json (atomic)
2. Update state.json
3. Print success + restart hint
```

### 6.5 Keyring Backend Strategy

```
Detection order:
1. Check if $DISPLAY or $WAYLAND_DISPLAY is set (graphical session)
2. Try `keyring.get_keyring()` — check if it's a real backend
3. If SecretService/KWallet available → use keyring mode
4. If headless or PlaintextKeyring → use file-only mode
5. User override: config.toml `storage_mode = "file"` forces file mode

Keyring services used:
- gemini-cli-oauth / main-account     → Gemini OAuth (matches CLI's own)
- cli-switcher-gemini / <label>        → Gemini API keys (our own)
- cli-switcher-codex / <label>         → Codex API keys (our own)
```

---

## 7. CLI Interface

### 7.1 Command Tree

```
switcher [status]                          Show dashboard of all CLIs
switcher <cli> list                        List profiles for <cli>
switcher <cli> switch <id>                 Switch to profile by index or label
switcher <cli> next                        Rotate to next profile
switcher <cli> add [label]                 Add new profile (interactive)
switcher <cli> remove <id>                 Remove profile
switcher <cli> import <path> [label]       Import credentials file
switcher <cli> health                      Check health of all profiles
switcher config [key] [value]              View or set config
switcher install                           Install shell + hook integration
switcher uninstall                         Remove shell + hook integration
switcher version                           Print version
```

Where `<cli>` is `gemini` or `codex`.
Where `<id>` is a 1-based index number or profile label/email.

### 7.2 Dashboard Output (`switcher status`)

```
╔══════════════════════════════════════════════════════╗
║  CLI Switcher v0.1.0                                 ║
╠══════════════════════════════════════════════════════╣
║                                                      ║
║  GEMINI CLI                                          ║
║  ─────────                                           ║
║  Active: work@gmail.com (OAuth)          ✅ valid    ║
║  Auto-rotate: OFF                                    ║
║                                                      ║
║  01. ● work@gmail.com        OAuth    ✅ valid       ║
║  02. ○ personal@gmail.com    OAuth    ⚠️  expiring   ║
║  03. ○ project-key           API Key  ✅ valid       ║
║                                                      ║
║  CODEX CLI                                           ║
║  ─────────                                           ║
║  Active: work-apikey (API Key)           ✅ valid    ║
║                                                      ║
║  01. ● work-apikey           API Key  ✅ valid       ║
║  02. ○ chatgpt-pro           ChatGPT  ✅ valid       ║
║                                                      ║
╚══════════════════════════════════════════════════════╝
```

### 7.3 Argument Parsing

Use `argparse` with subparsers. No third-party CLI frameworks.

```python
# Top level
parser = argparse.ArgumentParser(prog="switcher")
subparsers = parser.add_subparsers(dest="command")

# switcher gemini ...
gemini_parser = subparsers.add_parser("gemini")
gemini_sub = gemini_parser.add_subparsers(dest="action")
gemini_sub.add_parser("list")
switch_p = gemini_sub.add_parser("switch")
switch_p.add_argument("target")
# ... etc for each action

# switcher codex ...
# (mirror of gemini)

# switcher config ...
config_parser = subparsers.add_parser("config")
config_parser.add_argument("key", nargs="?")
config_parser.add_argument("value", nargs="?")

# switcher install / uninstall
subparsers.add_parser("install")
subparsers.add_parser("uninstall")
```

---

## 8. Hook System

### 8.1 Gemini AfterAgent Hook

**Trigger:** Runs after every agent response.
**Input (stdin):** JSON with `prompt_response`, `session_id`, `cwd`, etc.
**Logic:**

```
1. Parse stdin JSON
2. Check if auto-rotate is enabled in config
3. Match prompt_response against quota error patterns:
   - "429", "Resource exhausted", "Quota exceeded"
   - "Usage limit reached", "limit reached for all.*models"
   - "RESOURCE_EXHAUSTED", "PERMISSION_DENIED.*VALIDATION_REQUIRED"
4. If no match → output {} and exit 0
5. If match:
   a. Read retry_count from state.json
   b. If retry_count >= max_retries → log warning, reset, exit
   c. Call `switcher gemini next` (subprocess)
   d. Increment retry_count in state.json
   e. Output: {"decision": "retry", "systemMessage": "🔄 Switched to <account>. Retrying..."}
```

### 8.2 Gemini BeforeAgent Hook

**Trigger:** Runs before every agent request.
**Input (stdin):** JSON with `prompt`, `session_id`, etc.
**Logic:**

```
1. Parse stdin JSON
2. Check if auto-rotate + pre-check is enabled
3. Load quota cache from state or file
4. If cache valid (< cache_minutes old) → use cached data
5. If cache expired:
   a. Load OAuth token from active profile
   b. Call loadCodeAssist API → get project ID
   c. Call retrieveUserQuota API → get per-model remainingFraction
   d. Save to cache
6. Apply strategy:
   - conservative: switch only if ALL models < threshold
   - gemini3-first: switch if any model matching pattern < threshold
7. If switch needed:
   a. Call `switcher gemini next`
   b. Output: {"systemMessage": "⚡ Quota low — switched to <account>. Please /clear and retry."}
8. If no switch needed → output {}
```

### 8.3 Hook Installation

Hooks are registered in `~/.gemini/settings.json` by `switcher install`:

```json
{
  "hooks": {
    "AfterAgent": [{
      "matcher": "*",
      "hooks": [{
        "name": "switcher-auto-rotate",
        "type": "command",
        "command": "python3 /home/<user>/.config/cli-switcher/hooks/gemini_after_agent.py",
        "timeout": 10000,
        "description": "Auto-switch on quota exhaustion"
      }]
    }],
    "BeforeAgent": [{
      "matcher": "*",
      "hooks": [{
        "name": "switcher-pre-check",
        "type": "command",
        "command": "python3 /home/<user>/.config/cli-switcher/hooks/gemini_before_agent.py",
        "timeout": 10000,
        "description": "Pre-check quota before request"
      }]
    }]
  }
}
```

**Idempotent:** Installer checks if hooks already exist by `name` before adding.
**Merge-safe:** Preserves existing hooks in `settings.json`.

---

## 9. Shell Integration

### 9.1 What `switcher install` Does

1. **Detect shell** — check `$SHELL` for bash, zsh, fish
2. **Create env.sh** at `~/.config/cli-switcher/env.sh`
3. **Inject into shell RC** (`~/.bashrc` or `~/.zshrc`):

```bash
# --- CLI Switcher (auto-generated) ---
[ -f "$HOME/.config/cli-switcher/env.sh" ] && source "$HOME/.config/cli-switcher/env.sh"
alias sw='switcher'
# Shell wrappers to source env before CLI launch
gemini() { source "$HOME/.config/cli-switcher/env.sh" 2>/dev/null; command gemini "$@"; }
codex() { source "$HOME/.config/cli-switcher/env.sh" 2>/dev/null; command codex "$@"; }
# --- End CLI Switcher ---
```

4. **Install hooks** into `~/.gemini/settings.json` (if auto-rotate enabled)
5. **Install slash command** at `~/.gemini/commands/change.toml`:

```toml
description = "Switch Gemini account. Usage: /change <index|email|next>"
prompt = "!{python3 \"<path_to_switcher_main>\" gemini switch {{args}}}"
```

6. **Create symlink** (optional) at `~/.local/bin/switcher` → `main.py`

### 9.2 What `switcher uninstall` Does

1. Remove injected lines from shell RC (between marker comments)
2. Remove hooks from `~/.gemini/settings.json` (by name match)
3. Remove `~/.gemini/commands/change.toml`
4. Remove `~/.local/bin/switcher` symlink
5. Keep profiles and config (data is preserved)

---

## 10. Health Check System

### 10.1 Check Types

| Auth Type | CLI | Method | What It Validates |
|-----------|-----|--------|-------------------|
| Google OAuth | Gemini | POST to `https://oauth2.googleapis.com/token` with `refresh_token` | Token is still valid and refreshable |
| Gemini API Key | Gemini | GET `https://generativelanguage.googleapis.com/v1/models?key=<key>&pageSize=1` | Key is valid and not revoked |
| OpenAI API Key | Codex | GET `https://api.openai.com/v1/models` with `Authorization: Bearer <key>` | Key is valid |
| ChatGPT OAuth | Codex | POST to `https://auth.openai.com/oauth/token` with `refresh_token` | Token is refreshable |

### 10.2 Health Statuses

- **`valid`** — Token/key verified successfully
- **`expiring`** — OAuth token expires within 24 hours and refresh_token exists
- **`expired`** — Access token expired, refresh_token also failed
- **`revoked`** — 401/403 response indicating account revocation
- **`unknown`** — Never checked or network error during check

### 10.3 Check Schedule

- On explicit `switcher <cli> health` command
- On `switcher status` dashboard (uses cached health, max 1 hour old)
- On `switcher <cli> switch` — pre-switch validation of target profile
- Hooks do NOT run health checks (too slow for hook timeout)

---

## 11. Error Handling & Logging

### 11.1 Exception Hierarchy

```python
class SwitcherError(Exception):
    """Base exception for all switcher errors."""

class ProfileNotFoundError(SwitcherError):
    """Requested profile does not exist."""

class ProfileCorruptError(SwitcherError):
    """Profile directory exists but credentials are missing/invalid."""

class AuthError(SwitcherError):
    """Authentication operation failed."""

class KeyringError(AuthError):
    """Keyring read/write failed."""

class TokenExpiredError(AuthError):
    """Token refresh failed — re-login needed."""

class ConfigError(SwitcherError):
    """Configuration file is missing or invalid."""

class HookError(SwitcherError):
    """Hook execution failed."""
```

### 11.2 Logging

- Log to `~/.config/cli-switcher/logs/switcher.log`
- Use Python `logging` with `RotatingFileHandler` (max 1MB, 3 backups)
- Log levels configurable via `config.toml`
- Hooks log to stderr (visible in Gemini CLI debug output)
- User-facing output goes to stdout via `ui.py` — never mixed with log output

### 11.3 Graceful Degradation

| Failure | Behavior |
|---------|----------|
| Keyring unavailable | Fall back to file-only mode, log warning |
| Quota API unreachable | Skip pre-check, log warning, continue normally |
| Health check fails (network) | Set status to `unknown`, don't block switch |
| Hook script crashes | Output `{}` + `exit(0)` — never crash the parent CLI |
| State file corrupted | Regenerate from filesystem (scan profile dirs) |
| Config file missing | Use defaults, create on first write |

---

## 12. Dependencies

| Package | Version | Purpose | Required |
|---------|---------|---------|----------|
| `keyring` | >=25.0 | OS keyring access (GNOME Keyring / KWallet / SecretService) | Optional (file fallback) |
| `requests` | >=2.28 | HTTP calls for health checks and quota API | Required for health/hooks |
| `tomli` | >=2.0 | TOML parsing (backport for Python <3.11) | Required (Python <3.11 only) |
| `tomli-w` | >=1.0 | TOML writing | Required |

Install: `pip install keyring requests tomli-w`

Python 3.11+ has `tomllib` in stdlib, so `tomli` is only needed for 3.10.

---

## 13. Source File Map

| File | Lines (est.) | Responsibility |
|------|-------------|----------------|
| `main.py` | 15 | Entry point — imports and calls `switcher.cli.main()` |
| `switcher/__init__.py` | 5 | Package version |
| `switcher/errors.py` | 40 | Exception hierarchy |
| `switcher/utils.py` | 120 | XDG paths, platform detection, file locking, logging setup |
| `switcher/config.py` | 100 | TOML config load/save/defaults |
| `switcher/state.py` | 90 | State JSON read/write with file locking |
| `switcher/ui.py` | 150 | ANSI colors, table rendering, dashboard |
| `switcher/cli.py` | 250 | argparse setup, command routing, top-level orchestration |
| `switcher/profiles/base.py` | 80 | Abstract `ProfileManager` (list/add/remove/switch/next) |
| `switcher/profiles/gemini.py` | 200 | Gemini profile operations + symlink logic |
| `switcher/profiles/codex.py` | 160 | Codex profile operations + symlink logic |
| `switcher/auth/keyring_backend.py` | 100 | Keyring detection, read/write, file fallback |
| `switcher/auth/gemini_auth.py` | 130 | Gemini credential R/W (file + keyring + cache clear) |
| `switcher/auth/codex_auth.py` | 90 | Codex auth.json + env var handling |
| `switcher/health.py` | 150 | Token validation for all 4 auth types |
| `switcher/hooks/gemini_after_agent.py` | 120 | AfterAgent hook (standalone, quota detection) |
| `switcher/hooks/gemini_before_agent.py` | 140 | BeforeAgent hook (standalone, quota pre-check) |
| `switcher/installer.py` | 200 | Shell RC injection, hook install, slash command, env.sh |
| **Total** | **~2,140** | |

---

## 14. Detailed Task List

### Phase 0: Project Setup

- [x] **T-001** Create `pyproject.toml` with project metadata, Python >=3.10, dependencies (`keyring`, `requests`, `tomli-w`)
- [x] **T-002** Create package directory structure: `switcher/`, `switcher/profiles/`, `switcher/auth/`, `switcher/hooks/`, `tests/`
- [x] **T-003** Create all `__init__.py` files
- [x] **T-004** Create `switcher/errors.py` — exception hierarchy (`SwitcherError`, `ProfileNotFoundError`, `AuthError`, `KeyringError`, `TokenExpiredError`, `ConfigError`, `ProfileCorruptError`, `HookError`)

### Phase 1: Core Infrastructure

- [x] **T-005** Implement `switcher/utils.py`:
  - [x] T-005a: `get_config_dir()` — resolve `$XDG_CONFIG_HOME/cli-switcher` with fallback to `~/.config/cli-switcher`
  - [x] T-005b: `get_gemini_dir()` — resolve `~/.gemini`
  - [x] T-005c: `get_codex_dir()` — resolve `$CODEX_HOME` or `~/.codex`
  - [x] T-005d: `get_platform_string()` — return `"LINUX_AMD64"`, `"LINUX_ARM64"`, etc.
  - [x] T-005e: `setup_logging(level)` — configure `RotatingFileHandler` to `logs/switcher.log`
  - [x] T-005f: `file_lock(path)` — context manager using `fcntl.flock` for safe concurrent writes
  - [x] T-005g: `atomic_symlink(source, target)` — create symlink atomically via temp + `os.replace`
  - [x] T-005h: `ensure_dirs()` — create all required directories on first run

- [x] **T-006** Implement `switcher/config.py`:
  - [x] T-006a: `DEFAULT_CONFIG` dict matching config.toml schema
  - [x] T-006b: `load_config()` — read TOML, merge with defaults, return dict
  - [x] T-006c: `save_config(config)` — write TOML atomically
  - [x] T-006d: `get_config_value(key)` — dot-notation access (`"auto_rotate.threshold_percent"`)
  - [x] T-006e: `set_config_value(key, value)` — dot-notation set with type coercion

- [x] **T-007** Implement `switcher/state.py`:
  - [x] T-007a: `load_state()` — read `state.json` with file lock, return dict
  - [x] T-007b: `save_state(state)` — write `state.json` with file lock
  - [x] T-007c: `get_active_profile(cli_name)` — return active profile label for gemini/codex
  - [x] T-007d: `set_active_profile(cli_name, label)` — update active + timestamp
  - [x] T-007e: `get_rotation_state(cli_name)` — return retry_count, rotation_index
  - [x] T-007f: `update_rotation_state(cli_name, **kwargs)` — update retry count, etc.

- [x] **T-008** Implement `switcher/ui.py`:
  - [x] T-008a: ANSI color constants (detect `$NO_COLOR` and `$TERM`)
  - [x] T-008b: `print_success(msg)`, `print_error(msg)`, `print_warning(msg)`, `print_info(msg)`
  - [x] T-008c: `print_table(headers, rows)` — simple aligned table
  - [x] T-008d: `print_profile_list(profiles, active, cli_name)` — formatted profile listing
  - [x] T-008e: `print_dashboard(gemini_state, codex_state)` — full status dashboard
  - [x] T-008f: `confirm(prompt)` — y/N confirmation prompt

### Phase 2: Profile Management

- [x] **T-009** Implement `switcher/profiles/base.py`:
  - [x] T-009a: `ProfileManager` abstract class with methods: `list_profiles()`, `get_profile(id)`, `add_profile(label, auth_type)`, `remove_profile(id)`, `switch_to(id)`, `switch_next()`, `import_credentials(path, label)`
  - [x] T-009b: `Profile` dataclass: `label`, `auth_type` (oauth/apikey/chatgpt), `path`, `meta`, `is_active`
  - [x] T-009c: `load_meta(profile_dir)` / `save_meta(profile_dir, meta)` helper functions

- [x] **T-010** Implement `switcher/profiles/gemini.py`:
  - [x] T-010a: `GeminiProfileManager(ProfileManager)` constructor — sets profile dir, target paths
  - [x] T-010b: `list_profiles()` — scan `profiles/gemini/`, read each meta.json, sort
  - [x] T-010c: `add_profile(label, auth_type)` — create dir, prompt for credentials or copy current
  - [x] T-010d: `remove_profile(id)` — validate not active, confirm, delete dir, update state
  - [x] T-010e: `switch_to(id)` — resolve id→label, call appropriate auth handler (OAuth or API key)
  - [x] T-010f: `switch_next()` — get sorted profiles, find current index, advance, call switch_to
  - [x] T-010g: `import_credentials(path, label)` — validate file, detect auth type, copy to profile dir

- [x] **T-011** Implement `switcher/profiles/codex.py`:
  - [x] T-011a: `CodexProfileManager(ProfileManager)` constructor
  - [x] T-011b: `list_profiles()` — scan `profiles/codex/`, read meta
  - [x] T-011c: `add_profile(label, auth_type)` — create dir, prompt for API key or copy current auth.json
  - [x] T-011d: `remove_profile(id)` — validate, confirm, delete
  - [x] T-011e: `switch_to(id)` — resolve id→label, call appropriate auth handler
  - [x] T-011f: `switch_next()` — rotate through profiles
  - [x] T-011g: `import_credentials(path, label)` — validate auth.json format, copy

### Phase 3: Auth Backends

- [x] **T-012** Implement `switcher/auth/keyring_backend.py`:
  - [x] T-012a: `detect_keyring_mode()` — check `$DISPLAY`, probe keyring backend, return "keyring" or "file"
  - [x] T-012b: `keyring_read(service, key)` — read from OS keyring, return JSON string or None
  - [x] T-012c: `keyring_write(service, key, value)` — write JSON string to keyring
  - [x] T-012d: `keyring_delete(service, key)` — delete keyring entry
  - [x] T-012e: Error wrapping — catch `keyring.errors.*` → raise `KeyringError`

- [x] **T-013** Implement `switcher/auth/gemini_auth.py`:
  - [x] T-013a: `backup_current_credentials(profile_label)` — save current `~/.gemini/oauth_creds.json` + keyring to profile dir
  - [x] T-013b: `activate_oauth_profile(profile_dir)` — atomic symlink + keyring write + cache clear
  - [x] T-013c: `activate_apikey_profile(api_key)` — write to `env.sh`, unset OAuth symlink if exists
  - [x] T-013d: `clear_gemini_cache()` — delete `mcp-oauth-tokens.json`
  - [x] T-013e: `convert_to_keyring_format(oauth_creds)` — transform `oauth_creds.json` → `HybridTokenStorage` JSON
  - [x] T-013f: `convert_from_keyring_format(keyring_json)` — reverse transform

- [x] **T-014** Implement `switcher/auth/codex_auth.py`:
  - [x] T-014a: `activate_apikey_profile(profile_dir)` — symlink auth.json + write env.sh
  - [x] T-014b: `activate_chatgpt_profile(profile_dir)` — symlink auth.json
  - [x] T-014c: `detect_auth_type(auth_json_path)` — parse auth.json, return "apikey" or "chatgpt"
  - [x] T-014d: `extract_api_key(auth_json_path)` — read OPENAI_API_KEY from auth.json
  - [x] T-014e: `write_env_sh(gemini_key, codex_key)` — generate/update env.sh with both keys

### Phase 4: CLI Interface

- [x] **T-015** Implement `switcher/cli.py`:
  - [x] T-015a: `build_parser()` — construct argparse parser with all subcommands
  - [x] T-015b: `cmd_status(args)` — load state for both CLIs, call `ui.print_dashboard()`
  - [x] T-015c: `cmd_list(args, cli_name)` — get profile manager, list, print table
  - [x] T-015d: `cmd_switch(args, cli_name)` — get profile manager, switch, print result
  - [x] T-015e: `cmd_next(args, cli_name)` — get profile manager, switch_next, print result
  - [x] T-015f: `cmd_add(args, cli_name)` — interactive or label-based add
  - [x] T-015g: `cmd_remove(args, cli_name)` — with confirmation prompt
  - [x] T-015h: `cmd_import(args, cli_name)` — validate file, import
  - [x] T-015i: `cmd_health(args, cli_name)` — run health checks, print results
  - [x] T-015j: `cmd_config(args)` — show or set config values
  - [x] T-015k: `cmd_install(args)` — call installer
  - [x] T-015l: `cmd_uninstall(args)` — call uninstaller
  - [x] T-015m: `main()` — parse args, route to handler, catch SwitcherError, exit codes

- [x] **T-016** Update `main.py`:
  - [x] T-016a: Import and call `switcher.cli.main()`
  - [x] T-016b: Add `#!/usr/bin/env python3` shebang
  - [x] T-016c: Make executable (`chmod +x`)

### Phase 5: Health Checks

- [x] **T-017** Implement `switcher/health.py`:
  - [x] T-017a: `check_gemini_oauth(profile_dir)` — attempt token refresh via Google endpoint
  - [x] T-017b: `check_gemini_apikey(api_key)` — minimal `models.list` API call
  - [x] T-017c: `check_codex_apikey(api_key)` — minimal OpenAI `models` API call
  - [x] T-017d: `check_codex_chatgpt(profile_dir)` — attempt token refresh via OpenAI endpoint
  - [x] T-017e: `check_profile(cli_name, profile)` — dispatch to correct check based on auth_type
  - [x] T-017f: `check_all_profiles(cli_name)` — iterate profiles, update meta.json with results
  - [x] T-017g: `interpret_http_status(status_code)` — map 200/401/403/429 → health_status enum

### Phase 6: Hooks (Auto-Rotation)

- [x] **T-018** Implement `switcher/hooks/gemini_after_agent.py`:
  - [x] T-018a: Read stdin JSON → extract `prompt_response`
  - [x] T-018b: `QUOTA_ERROR_PATTERNS` list — regex patterns for quota errors
  - [x] T-018c: `is_quota_error(response)` — match against patterns
  - [x] T-018d: Load config and check `auto_rotate.enabled`
  - [x] T-018e: Retry count management via `state.json` (with file lock)
  - [x] T-018f: Call `switcher gemini next` via subprocess on match
  - [x] T-018g: Output JSON `{"decision": "retry", "systemMessage": "..."}` on successful switch
  - [x] T-018h: Reset retry count on non-error responses (clear state)
  - [x] T-018i: Wrap everything in try/except → output `{}` on any error

- [x] **T-019** Implement `switcher/hooks/gemini_before_agent.py`:
  - [x] T-019a: Read stdin JSON → extract `session_id`, `prompt`
  - [x] T-019b: Quota cache loading from `state.json` (check TTL)
  - [x] T-019c: API calls: `loadCodeAssist` → get project_id, `retrieveUserQuota` → get buckets
  - [x] T-019d: Platform detection for API metadata (use `get_platform_string()`)
  - [x] T-019e: Strategy evaluation — conservative vs gemini3-first
  - [x] T-019f: Call `switcher gemini next` if switch needed
  - [x] T-019g: Save quota data to cache with timestamp
  - [x] T-019h: Output `{"systemMessage": "..."}` if switched, else `{}`
  - [x] T-019i: Wrap in try/except → output `{}` on any error

### Phase 7: Installer

- [ ] **T-020** Implement `switcher/installer.py`:
  - [ ] T-020a: `detect_shell()` — check `$SHELL`, return "bash", "zsh", or "fish"
  - [ ] T-020b: `get_rc_file(shell)` — return path to `.bashrc`, `.zshrc`, or `config.fish`
  - [ ] T-020c: `generate_shell_snippet()` — build the shell integration block with marker comments
  - [ ] T-020d: `inject_into_rc(rc_path, snippet)` — append snippet if not already present (idempotent)
  - [ ] T-020e: `remove_from_rc(rc_path)` — remove lines between marker comments
  - [ ] T-020f: `install_gemini_hooks(settings_path)` — merge hooks into settings.json (idempotent)
  - [ ] T-020g: `remove_gemini_hooks(settings_path)` — remove hooks by name from settings.json
  - [ ] T-020h: `install_slash_command(commands_dir)` — write `change.toml`
  - [ ] T-020i: `remove_slash_command(commands_dir)` — delete `change.toml`
  - [ ] T-020j: `generate_env_sh()` — write `env.sh` based on current active API key profiles
  - [ ] T-020k: `install_bin_symlink()` — symlink to `~/.local/bin/switcher`
  - [ ] T-020l: `remove_bin_symlink()` — remove the symlink
  - [ ] T-020m: `copy_hook_scripts()` — copy hook .py files to `~/.config/cli-switcher/hooks/`
  - [ ] T-020n: `run_install()` — orchestrate all install steps, print summary
  - [ ] T-020o: `run_uninstall()` — orchestrate all uninstall steps, print summary

### Phase 8: Polish & Testing

- [ ] **T-021** Status dashboard:
  - [ ] T-021a: Wire `cmd_status()` to gather all profile + health data
  - [ ] T-021b: Handle edge case: no profiles for a CLI
  - [ ] T-021c: Handle edge case: CLIs not installed

- [ ] **T-022** Error handling sweep:
  - [ ] T-022a: Ensure all user-facing commands catch `SwitcherError` and print friendly messages
  - [ ] T-022b: Ensure all file operations handle `PermissionError`, `FileNotFoundError`
  - [ ] T-022c: Ensure hooks never exit non-zero (always `sys.exit(0)`)

- [ ] **T-023** Edge cases:
  - [ ] T-023a: First run — no config, no profiles, no state → create defaults
  - [ ] T-023b: Broken symlink detection → warn and offer repair
  - [ ] T-023c: Profile dir exists but creds missing → `ProfileCorruptError`
  - [ ] T-023d: Only one profile → `switch_next()` warns "only one account"
  - [ ] T-023e: Active profile deleted externally → detect and clear state

- [ ] **T-024** Documentation:
  - [ ] T-024a: Write `README.md` — installation, quickstart, full command reference
  - [ ] T-024b: Add inline docstrings to all public functions
  - [ ] T-024c: Update `docs/spec.md` if design changed during implementation

- [ ] **T-025** Manual testing on Ubuntu:
  - [ ] T-025a: Test with real Gemini CLI — add 2 OAuth profiles, switch, verify CLI uses new account
  - [ ] T-025b: Test with real Codex CLI — add API key profile, switch, verify
  - [ ] T-025c: Test keyring mode (GNOME session) — verify credentials appear in Seahorse
  - [ ] T-025d: Test file-only mode (SSH session) — verify fallback works
  - [ ] T-025e: Test `switcher install` — verify shell RC modified, hooks in settings.json
  - [ ] T-025f: Test `switcher uninstall` — verify clean removal
  - [ ] T-025g: Test auto-rotate hook — simulate quota error response, verify switch + retry
  - [ ] T-025h: Test health checks — verify status for valid, expired, and revoked tokens

---

## 15. Open Questions & Risks

### Open Questions

| # | Question | Default Assumption |
|---|----------|--------------------|
| 1 | Should we support Fish shell in addition to bash/zsh? | Bash + zsh only for v0.1 |
| 2 | Should `switcher gemini add` auto-detect from current `~/.gemini/oauth_creds.json`? | Yes — offer to import current creds |
| 3 | Should we encrypt API keys at rest (beyond keyring)? | No — keyring provides OS-level encryption |
| 4 | Should the tool manage `GEMINI_API_KEY` and `GOOGLE_API_KEY` separately? | Treat as aliases — set both |
| 5 | Should quota API calls use a longer timeout on slow networks? | 10s default, configurable |
| 6 | Should we support `$CODEX_HOME` override for non-standard Codex installs? | Yes — read from env |

### Risks

| # | Risk | Mitigation |
|---|------|------------|
| 1 | **Gemini CLI keyring format changes** — `HybridTokenStorage` schema is not a public API | Pin to known working format, add version detection, test on each CLI update |
| 2 | **`v1internal` quota API breaks** — undocumented internal API | Quota features are optional; core switching works without API. Graceful fallback. |
| 3 | **Codex CLI auth.json format changes** — Codex is actively developed | Version-detect the format, support both current schemas |
| 4 | **Keyring daemon not running** — headless Ubuntu Server | Auto-detect and fall back to file mode. Clear warning to user. |
| 5 | **Symlink not followed by CLI** — some tool may `realpath()` before reading | Test empirically. Fallback: atomic file copy instead of symlink. |
| 6 | **Concurrent hook invocations corrupt state** — two hooks fire simultaneously | File locking (`fcntl.flock`) on all state writes |

---

## 16. Python Coding Standards (Researched Feb 2026)

> Based on web research of PEP 8, Python 3.11–3.14 what's-new pages, modern
> packaging guide (pyproject.toml), Ruff docs, and mypy getting-started.

### 16.1 Language Target

- **Minimum: Python 3.10** (Ubuntu 22.04 ships 3.10, Ubuntu 24.04 ships 3.12)
- Use `from __future__ import annotations` to enable PEP 604 union syntax (`X | Y`) at runtime on 3.10
- Use `tomllib` (stdlib 3.11+) with `tomli` fallback for 3.10 compat
- Avoid Python 3.12+ only features (PEP 695 type param syntax `def f[T]()`) to stay 3.10-compatible

### 16.2 Type Hints (PEP 484 / PEP 604)

- **All public functions and methods must have full type annotations** (args + return)
- Use modern union syntax: `str | None` instead of `Optional[str]` (via `__future__` import)
- Use `collections.abc.Iterable`, `collections.abc.Sequence` etc. instead of `typing.List`, `typing.Dict`
- Use `pathlib.Path` for all filesystem paths in type signatures
- Private helpers may omit annotations (mypy `--check-untyped-defs` will still check)
- Dataclasses or `TypedDict` for structured data (prefer `dataclasses.dataclass` for mutable state, `TypedDict` for JSON shapes)

### 16.3 Formatting & Linting — Ruff

- **Use Ruff** (not Black + Flake8 + isort separately) — single tool, 100x faster
- Line length: **88** (Ruff/Black default, wider than PEP 8's 79 but industry standard)
- Indent: **4 spaces**
- Quote style: **double quotes** (Ruff default)
- Enable rule sets: `["E", "F", "W", "I", "B", "UP", "RUF", "SIM", "TCH"]`
  - `E/F/W` = pycodestyle + pyflakes
  - `I` = isort
  - `B` = flake8-bugbear
  - `UP` = pyupgrade (modernize syntax)
  - `RUF` = Ruff-specific rules
  - `SIM` = simplify
  - `TCH` = type-checking imports
- Config lives in `pyproject.toml` under `[tool.ruff]`

### 16.4 Static Type Checking — mypy

- Use `mypy --strict` in CI (with per-module overrides as needed)
- Config in `pyproject.toml` under `[tool.mypy]`
- `warn_return_any = true`, `disallow_untyped_defs = true`

### 16.5 Packaging (pyproject.toml — PEP 621)

- **Build backend: `hatchling`** (or `setuptools>=77` if simpler)
- All metadata in `[project]` table (not `setup.cfg` or `setup.py`)
- Use `[project.scripts]` for CLI entry point: `switcher = "switcher.cli:main"`
- `requires-python = ">= 3.10"`
- License: SPDX expression in `license` field (PEP 639)
- Dependencies in `[project.dependencies]`, dev-deps in `[project.optional-dependencies]`

### 16.6 Testing — pytest

- Use `pytest` (not unittest) with `pytest-cov` for coverage
- Test files: `tests/` directory mirroring `switcher/` structure
- Fixtures in `conftest.py` (tmp dirs, mock keyring, fake CLI dirs)
- Target: **≥80% line coverage**

### 16.7 Code Style Notes (PEP 8 Highlights)

- Two blank lines around top-level definitions
- Single blank line around methods
- Imports: stdlib → third-party → local, separated by blank lines
- Constants: `UPPER_SNAKE_CASE`
- Classes: `PascalCase`
- Functions/variables: `lower_snake_case`
- Private: single `_` prefix, never double `__` (name mangling)
- Docstrings: Google style (`Args:`, `Returns:`, `Raises:`)
- Comments only when intent isn't obvious from code

### 16.8 Modern Python Features to Use

| Feature | PEP | Use case |
|---------|-----|----------|
| `match` statement | PEP 634 (3.10) | CLI command dispatch |
| `X \| Y` union types | PEP 604 (3.10) | All type hints |
| `dataclasses.dataclass(slots=True)` | PEP 681 (3.10) | State/config objects |
| `tomllib` | PEP 680 (3.11) | Config parsing (with tomli fallback) |
| `ExceptionGroup` | PEP 654 (3.11) | Multi-error reporting (optional) |
| `pathlib.Path` | stdlib | All file paths |
| `contextlib.suppress` | stdlib | Clean error ignoring |
| `functools.cache` | stdlib | Memoize expensive lookups |

---

## 17. Additional Codebase Findings (Deep Dive Feb 2026)

> Details discovered from thorough reading of all relevant source files in
> `google-gemini/gemini-cli` and `openai/codex`.

### 17.1 Gemini CLI — New Findings

**Config system** (`packages/core/src/config/config.ts` — 81KB):
- Main config class `Config` is enormous; handles model selection, proxy, safety, hooks, memory, skills, agents, extensions
- Settings file path: `~/.gemini/settings.json` (user level), also workspace-level `.gemini/settings.json`
- System-level settings: `/etc/gemini-cli/settings.json` on Linux
- Env override: `GEMINI_CLI_SYSTEM_SETTINGS_PATH`

**Auth type detection** (`packages/core/src/core/contentGenerator.ts`):
- Priority order: `GOOGLE_GENAI_USE_GCA=true` → OAuth; `GOOGLE_GENAI_USE_VERTEXAI=true` → Vertex AI; `GEMINI_API_KEY` → API key
- Also checks `GOOGLE_API_KEY` (for Vertex AI), `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION`
- **5 AuthType values**: `LOGIN_WITH_GOOGLE` (oauth-personal), `USE_GEMINI` (gemini-api-key), `USE_VERTEX_AI` (vertex-ai), `LEGACY_CLOUD_SHELL`, `COMPUTE_ADC`
- `GEMINI_API_KEY` env var takes direct precedence over `loadApiKey()` file
- Custom headers via `GEMINI_CLI_CUSTOM_HEADERS` env var
- API key auth mechanism configurable: `GEMINI_API_KEY_AUTH_MECHANISM` (default: `x-goog-api-key`, alt: `bearer`)

**Storage system** (`packages/core/src/config/storage.ts`):
- `Storage.getOAuthCredsPath()` → `~/.gemini/oauth_creds.json`
- `Storage.getMcpOAuthTokensPath()` → `~/.gemini/mcp-oauth-tokens.json` (NOT v2 — corrected)
- `Storage.getGlobalSettingsPath()` → `~/.gemini/settings.json`
- `Storage.getGoogleAccountsPath()` → `~/.gemini/google_accounts.json`
- Project-level data stored under `~/.gemini/tmp/<project-slug>/` and `~/.gemini/history/<project-slug>/`
- **Storage migration**: moving from hash-based to slug-based project directories

**Implications for switcher**:
- Must clear `~/.gemini/mcp-oauth-tokens.json` (not v2) on switch
- `google_accounts.json` may also need clearing/updating on switch
- Env var `GEMINI_API_KEY` takes precedence — our shell wrapper approach is correct
- System-level settings at `/etc/gemini-cli/settings.json` won't conflict with user hooks

### 17.2 Codex CLI — New Findings

**Auth system** (`codex-rs/core/src/auth.rs` — 58KB):
- `OPENAI_API_KEY` and `CODEX_API_KEY` — both checked, OPENAI takes precedence
- `AuthCredentialsStoreMode` has 3 variants: `File`, `Keyring`, `Ephemeral`
- `Ephemeral` mode stores in memory only (for external auth tokens passed by parent apps)
- Auth storage is abstracted via `codex-rs/core/src/auth/storage.rs` module
- **UnauthorizedRecovery state machine**: on 401 errors, Codex automatically (1) reloads from disk, (2) tries OAuth token refresh. If auth.json changes on disk, Codex picks up the new token without restart!
- `reload()` checks `account_id` — only reloads if the account ID in the file matches the running session's account ID. **This means our switcher must ensure account ID continuity or Codex will reject the reload**
- Token refresh URL: `https://auth.openai.com/oauth/token` (with env override `CODEX_REFRESH_TOKEN_URL`)
- `logout_all_stores()` clears both ephemeral and managed stores

**Codex directory structure**:
- `codex-cli/` = Node.js/TypeScript frontend (thin wrapper)
- `codex-rs/` = Rust core (does all the real work: auth, sandbox, agent)
- `sdk/` = additional packages
- The Rust core is the canonical auth implementation

**Implications for switcher**:
- Codex's `reload()` account_id check is a **potential blocker** for seamless switching while Codex is running
- Env var `OPENAI_API_KEY` approach bypasses this issue entirely (API key profiles are simpler)
- For ChatGPT OAuth profiles, Codex will need a restart unless account IDs are managed carefully
- The 3 storage modes mean we should target `File` mode for our switches (most reliable)

### 17.3 Corrections to Original Spec

| Item | Was | Corrected to |
|------|-----|-------------|
| MCP token cache path | `mcp-oauth-tokens-v2.json` | `mcp-oauth-tokens.json` |
| Gemini AuthType enum | 3 values assumed | 5 values: `LOGIN_WITH_GOOGLE`, `USE_GEMINI`, `USE_VERTEX_AI`, `LEGACY_CLOUD_SHELL`, `COMPUTE_ADC` |
| Codex storage modes | 2 assumed (file, keyring) | 3: `File`, `Keyring`, `Ephemeral` |
| Codex reload behavior | Simple file re-read | Account-ID-gated reload — rejects if account_id doesn't match running session |
| Env var priority | `GEMINI_API_KEY` checked alongside file | `GEMINI_API_KEY` env var takes **precedence** over `loadApiKey()` file read |
| Additional env vars | `GEMINI_API_KEY` only | Also: `GOOGLE_API_KEY`, `GOOGLE_GENAI_USE_GCA`, `GOOGLE_GENAI_USE_VERTEXAI`, `GOOGLE_CLOUD_PROJECT`, `GEMINI_CLI_CUSTOM_HEADERS`, `GEMINI_API_KEY_AUTH_MECHANISM` |

---

## Summary

**Total estimated tasks: 79** (T-001 through T-025h, with sub-tasks)

**Phases:**
- Phase 0: Project Setup — 4 tasks
- Phase 1: Core Infrastructure — 19 sub-tasks across 4 top tasks
- Phase 2: Profile Management — 17 sub-tasks across 3 top tasks
- Phase 3: Auth Backends — 16 sub-tasks across 3 top tasks
- Phase 4: CLI Interface — 16 sub-tasks across 2 top tasks
- Phase 5: Health Checks — 7 sub-tasks in 1 top task
- Phase 6: Hooks — 18 sub-tasks across 2 top tasks
- Phase 7: Installer — 15 sub-tasks in 1 top task
- Phase 8: Polish & Testing — 19 sub-tasks across 5 top tasks
