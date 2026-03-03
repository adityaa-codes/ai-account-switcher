# Gemini UX and Auto-Rotation Enhancements Plan

## Scope
Implement the following external-inspired features in this repo, excluding bilingual output:

1. `sw gemini menu` interactive command.
2. `sw gemini quota` command to show live quota buckets.
3. `/change` slash command parity (`/change`, `/change next`, `/change 2`, `/change email`).
4. `sw gemini pool` UX aliases (`pool`, `pool add`, `pool remove`, `pool import`).
5. Stronger quota-error detection patterns in AfterAgent hook.
6. Crash-safe handoff state file between AfterAgent and BeforeAgent hooks.
7. Optional auto-restart toggle after account switch.

## Brief Implementation Plan
1. Build shared quota/switch infrastructure first so all UX surfaces (`menu`, `quota`, hooks, slash) use one code path.
2. Add user-facing commands in this order: `menu` -> `quota` -> `pool` aliases -> `/change` argument handling.
3. Improve hook reliability with stronger quota detection, crash-safe state handoff, and optional restart.
4. Wire new config flags, tests, and docs before release.

## Detailed Task List

### Feature 1: `sw gemini menu` interactive command
1. Add CLI route in `switcher/cli.py` for `gemini menu`.
2. Implement a small menu controller module (suggested: `switcher/ui_menu.py`) that calls existing command handlers instead of duplicating logic.
3. Include actions: list profiles, switch profile, add profile, import profile, run quota check, edit auto-rotate config.
4. Ensure non-interactive fallback: if not TTY, print actionable command list and exit cleanly.
5. Add unit tests for menu action dispatch in `tests/test_cli_menu.py`.

### Feature 2: `sw gemini quota` command
1. Add CLI route in `switcher/cli.py` for `gemini quota`.
2. Extract reusable quota API logic into service module (suggested: `switcher/quota.py`).
3. Reuse active Gemini OAuth profile/token path from `switcher/state.py` and `switcher/profiles/gemini.py`.
4. Add output formatter in `switcher/ui.py` for quota buckets and low-quota highlighting.
5. Add config-driven threshold usage from `switcher/config.py`.
6. Add tests for success/error/expired-token paths in `tests/test_quota_command.py`.

### Feature 3: `/change` slash command parity
1. Add dedicated command path `switcher gemini change [target]` in `switcher/cli.py`.
2. Update installer command registration in `switcher/installer.py` to route `/change` to the new handler.
3. Implement argument parsing compatibility for slash input formats used by Gemini CLI.
4. If slash arguments are limited by Gemini CLI, add explicit fallback slash commands (`/change-next`, `/change-list`) and document exact behavior.
5. Add integration tests for target resolution (`index`, `label/email`, `next`) in `tests/test_change_command.py`.

### Feature 4: `pool` UX aliases
1. Add command group `switcher gemini pool` in `switcher/cli.py`.
2. Map `pool` to `list`, `pool add` to `add`, `pool remove` to `remove`, `pool import` to `import`.
3. Keep canonical commands unchanged; aliases should call existing code paths.
4. Add help text updates in `switcher/ui.py` and `README.md`.
5. Add tests for alias equivalence in `tests/test_pool_aliases.py`.

### Feature 5: Stronger quota-error detection in AfterAgent
1. Expand detection patterns in `switcher/hooks/gemini_after_agent.py` for known 429/resource-exhausted variants and structured error payloads.
2. Centralize patterns in one constant/module to share with BeforeAgent logic.
3. Add regression tests for false positives/false negatives in `tests/test_gemini_after_agent_patterns.py`.

### Feature 6: Crash-safe handoff file between hooks
1. Add persistent flag file in switcher config dir (suggested: `~/.config/cli-switcher/state/quota_error.json`) managed via `switcher/state.py`.
2. Write flag in AfterAgent before returning retry decision.
3. Read and clear flag in BeforeAgent before making API calls.
4. Add TTL/retry-count guard to avoid infinite switch loops.
5. Add tests in `tests/test_hook_handoff_state.py`.

### Feature 7: Optional auto-restart after switch
1. Add config key `auto_rotate.restart_on_switch` in `switcher/config.py` with default `false`.
2. Implement restart helper logic inside hooks (or new `switcher/hooks/restart.py`) using Linux-safe subprocess relaunch behavior.
3. Ensure restart is only attempted in hook context and only after successful switch.
4. Add loop protection marker so restart does not cascade.
5. Add tests for config gating and command construction in `tests/test_hook_restart.py`.

## Cross-Cutting Tasks
1. Update command docs in `README.md` for `menu`, `quota`, `pool`, and `/change` behavior.
2. Add troubleshooting section for hook/restart behavior.
3. Run full quality gate: `ruff check`, `ruff format --check`, `mypy switcher/`, `pytest`.
4. Bump version and changelog entry after all tests pass.
