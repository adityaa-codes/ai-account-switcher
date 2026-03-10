# Changelog

All notable changes to this project will be documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/) and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [0.3.0] — 2026-03-10

### Added

#### Gemini hook safety
- Hooks (`gemini_before_agent.py`, `gemini_after_agent.py`) now bail out immediately with `{}` when the `stopHookActive` flag is present in the hook input, preventing deadlocks introduced in Gemini CLI ≥ 0.33.
- `AfterAgent` retry response now explicitly includes `"stopHookActive": false` to prevent stale flag propagation.

#### API resilience
- `loadCodeAssist` calls now send the correct metadata body (`ideType`, `platform`, `pluginType`) and include `"mode": "HEALTH_CHECK"` to prevent billing side-effects.
- OAuth client discovery (`_discover_gemini_oauth_client`) tries three candidate paths inside `gemini-cli-core/dist/` and falls back gracefully with a warning.
- Discovered OAuth client credentials are cached in `~/.config/ai-account-switcher/cache/oauth_client.json` with a 24-hour TTL, reducing startup latency.
- `ProfileQuotaInfo` now exposes a `tier` field populated from `currentTier.tierName` in the quota API response.
- Unix epoch integer `reset_at` values returned by the quota API are now normalised to ISO-8601 strings.

#### Pool sub-commands
- `switcher gemini pool list` — lists rotation pool profiles.
- `switcher gemini pool health` — runs health checks across all pool profiles.
- `switcher gemini pool export [--dest DIR]` — exports all pool profiles to a directory.
- `switcher gemini pool status` — shows rotation state and next-up profile.
- Same four sub-commands available under `switcher codex pool`.

#### Codex per-profile isolation
- `switcher/auth/codex_memory.py` — snapshots and restores Codex conversation memory (SQLite DB and flat-file store) per profile on every switch.
- `switcher/auth/codex_plugins.py` — records installed plugin lists per profile; warns when profiles have diverging plugins.
- `switcher/auth/codex_sandbox.py` — snapshots and restores Codex `policy.toml` per profile on every switch.
- All three are automatically invoked by `CodexProfileManager.switch_to()`.

#### Alerts and diagnostics
- `switcher alerts [--lines N]` — tails the last N lines (default 20) of `errors.log`.
- `switcher version --check` — fetches PyPI to report whether a newer release is available.

#### Discrete logging
- `errors.log` — ERROR-level-only log file for quick triage, separate from the general `switcher.log`.
- `commands.log` — per-invocation log with command name, elapsed time, and exit status (OK / ERROR / INTERRUPT).

### Fixed

- `loadCodeAssist` 400 errors caused by incorrect request body format (was `{"supportedFeatures": [...]}`, now uses correct `{"metadata": {...}}` structure).
- Idempotent hook installation — `install_gemini_hooks()` now updates hooks in-place and removes stale entries rather than appending duplicates on every `switcher install`.
- `_format_reset_date()` no longer uses `%-d` (GNU-only `strftime` extension); replaced with `str(dt.day)` for portability across non-glibc systems.

### Changed

- Quota display in `switcher gemini quota` and `switcher gemini health` now shows **quota used %** instead of remaining %, matching user expectation ("high bar = problem").
- `switcher version` output updated to reflect v0.3.0.

---

## [0.2.0] — 2025-07-01

### Added
- Interactive numbered TUI menu (`switcher gemini menu`, `switcher codex menu`).
- Live quota display with visual progress bars (`switcher gemini quota`).
- Auto-rotation via Gemini CLI hooks (`gemini_before_agent`, `gemini_after_agent`).
- Handoff flag mechanism to skip redundant quota API calls after rotation.
- Crash-safe `restart_on_switch` option.
- `pool add`, `pool remove`, `pool import` sub-commands.
- `switcher install` / `switcher uninstall` for shell integration.
- Import/export profiles between machines.
- Keyring integration with file fallback for headless systems.
- Health check command (`switcher gemini health`, `switcher codex health`).
- `/change` slash command registered in `~/.gemini/commands/`.

### Fixed
- Atomic symlink swap using `os.replace` instead of unlink + create.
- File-lock (`fcntl.flock`) on all state JSON writes.

---

## [0.1.0] — 2025-05-15

### Added
- Initial release.
- Basic Gemini CLI profile management (list, switch, next, add, remove, import, export).
- Basic Codex CLI profile management.
- XDG-compliant config and state directories.
- API key and OAuth credential support.
- `env.sh` shell wrapper injection.
