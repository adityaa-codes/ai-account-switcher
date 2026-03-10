# Release Notes — v0.3.0

**Release date:** 2026-03-10

---

## Overview

v0.3.0 is a stability, resilience, and isolation release. It fixes a long-standing 400 error from the Gemini quota API, hardens the hook system against a breaking change in Gemini CLI ≥ 0.33, adds per-profile isolation for Codex, expands pool management commands, and improves day-to-day observability with discrete log files and new diagnostic commands.

---

## Upgrade

```bash
git pull
pip install -e .
switcher install   # re-registers hooks (now idempotent — safe to re-run)
```

---

## What's New

### 🛡️ Hook safety — `stopHookActive` support

Gemini CLI ≥ 0.33 sets `stopHookActive: true` in hook input JSON when the agent loop is stopped by the user. Both `gemini_before_agent` and `gemini_after_agent` now detect this flag and return `{}` immediately, preventing an infinite retry loop that could hang the CLI.

### 🔧 Health command — fixed 400 errors

The `loadCodeAssist` API requires a specific metadata payload. The previous implementation sent `{"supportedFeatures": ["GEMINI_CLI"]}`, which caused HTTP 400 responses. The correct body is now sent:

```json
{
  "metadata": {
    "ideType": "GEMINI_CLI",
    "platform": "PLATFORM_UNSPECIFIED",
    "pluginType": "GEMINI"
  },
  "mode": "HEALTH_CHECK"
}
```

The `mode: HEALTH_CHECK` field also prevents billing side-effects during validation.

### 🔑 OAuth client caching

The OAuth client credentials needed to call Google's token API are now discovered automatically from the local `gemini-cli-core` package and cached for 24 hours at `~/.config/ai-account-switcher/cache/oauth_client.json`. This eliminates repeated filesystem scans on every health check.

### 🔄 Pool management commands

Four new sub-commands under `switcher gemini pool` (and `switcher codex pool`):

| Command | What it does |
|---|---|
| `pool list` | Lists all profiles in the rotation pool |
| `pool health` | Runs health checks across the pool |
| `pool export [--dest DIR]` | Exports all pool profiles to a directory |
| `pool status` | Shows rotation state and the next-up profile |

### 🧠 Codex per-profile isolation

When switching Codex profiles, the tool now automatically:

1. **Snapshots** the departing profile's conversation memory, plugin list, and sandbox policy.
2. **Restores** the incoming profile's memory and policy from the snapshot.
3. **Warns** if the two profiles have different plugins installed.

Memory is stored per profile under `~/.config/ai-account-switcher/profiles/codex/<label>/`.

### 📝 Per-profile system prompt (Gemini)

Add a `system_md` path to a Gemini profile's `meta.json` and `env.sh` will automatically export `GEMINI_SYSTEM_MD` whenever you switch to that profile:

```json
{
  "label": "work",
  "system_md": "/home/you/prompts/work.md"
}
```

### 📊 Quota display — used % instead of remaining %

The progress bars in `switcher gemini quota` and `switcher gemini health` now display **quota used** rather than quota remaining. A fuller bar now means more quota has been consumed, which is the more intuitive direction.

### 🔔 Alerts command

```bash
switcher alerts          # last 20 lines from errors.log
switcher alerts --lines 50
```

A quick way to see recent errors without opening the log file manually.

### 🔍 Version update check

```bash
switcher version --check
```

Fetches the PyPI JSON API and prints whether a newer version is available.

### 📁 Discrete log files

Two new log files complement the existing `switcher.log`:

| File | Contents |
|---|---|
| `logs/errors.log` | ERROR-level entries only — the fast triage file |
| `logs/commands.log` | One line per command: name, elapsed ms, exit status |

---

## Bug Fixes

| # | Description |
|---|---|
| — | `loadCodeAssist` returned HTTP 400 due to wrong request body format |
| — | `switcher install` appended duplicate hook entries on repeated runs; now idempotent |
| — | `_format_reset_date()` used `%-d` (GNU strftime only); fixed for portability |

---

## Breaking Changes

None. All existing commands and configuration files remain compatible.

---

## Test Suite

471 tests passing. New tests cover:
- Hook `stopHookActive` handling
- `loadCodeAssist` request format and tier/timestamp parsing
- OAuth client cache read/write/expiry
- Idempotent hook installation
- All four `pool` sub-commands
- Codex memory, plugin, and sandbox isolation
- `alerts` command and `version --check`
