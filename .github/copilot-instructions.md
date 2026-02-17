# Copilot Instructions — CLI Switcher

## What This Project Is

A Python CLI tool (`switcher`) that manages multiple authentication profiles for **Google Gemini CLI** and **OpenAI Codex CLI** on Ubuntu/Linux. It enables instant account switching via atomic symlinks and env-var shell wrappers, optional auto-rotation on Gemini quota exhaustion via hooks, and keyring integration with file fallback.

The full technical specification lives in `docs/spec.md` — read it before making architectural decisions.

## Build & Run

```bash
# Install in editable mode (once package structure exists)
pip install -e ".[dev]"

# Run directly
python main.py [command]

# Run a single test
pytest tests/test_config.py -v

# Run all tests with coverage
pytest --cov=switcher --cov-report=term-missing

# Lint and format
ruff check switcher/ tests/
ruff format switcher/ tests/

# Type check
mypy switcher/
```

## Architecture

### Two-CLI unified manager

`switcher/profiles/gemini.py` and `switcher/profiles/codex.py` both inherit from the abstract `ProfileManager` in `switcher/profiles/base.py`. The CLI layer (`switcher/cli.py`) routes `switcher gemini <action>` and `switcher codex <action>` to the appropriate manager. All state is under `~/.config/cli-switcher/` (XDG-compliant), not in the target CLIs' own directories.

### Switching mechanism

- **OAuth profiles**: Atomic symlink swap (`~/.gemini/oauth_creds.json` → profile dir) + keyring write to match Gemini CLI's `HybridTokenStorage` (service: `gemini-cli-oauth`, key: `main-account`). Must also delete `~/.gemini/mcp-oauth-tokens.json` (token cache).
- **API key profiles**: Write env vars to `~/.config/cli-switcher/env.sh`, which shell wrappers source before launching CLIs. No restart needed.
- Codex uses the same symlink pattern for `~/.codex/auth.json`. Codex's `reload()` is account-ID-gated — API key profiles work seamlessly, but ChatGPT OAuth profiles may require a Codex restart.

### Hook system (Gemini only)

`switcher/hooks/gemini_after_agent.py` and `gemini_before_agent.py` are standalone scripts registered in `~/.gemini/settings.json`. They run as subprocesses of Gemini CLI, read stdin JSON, and output `{"decision": "retry", "systemMessage": "..."}` to trigger auto-rotation. **Hooks must never exit non-zero or output invalid JSON** — always wrap in try/except and fall back to `{}`.

### Auth backend layering

`switcher/auth/keyring_backend.py` detects whether a real keyring daemon is available (`$DISPLAY`/`$WAYLAND_DISPLAY` + probe). Falls back to file-only mode on headless systems. `switcher/auth/gemini_auth.py` and `codex_auth.py` handle the CLI-specific credential formats and coordinate with the keyring backend.

## Key Conventions

### Python standards

- **Python 3.10+** — use `from __future__ import annotations` for PEP 604 union syntax
- **Ruff** for linting and formatting (line-length=88, rule sets: E,F,W,I,B,UP,RUF,SIM,TCH)
- **mypy --strict** for type checking
- `pathlib.Path` for all filesystem paths, never raw strings
- `dataclasses.dataclass(slots=True)` for structured data
- Google-style docstrings (`Args:`, `Returns:`, `Raises:`)
- `argparse` for CLI — no third-party CLI frameworks (Click, Typer, etc.)

### File safety patterns

- All state file writes use `fcntl.flock` via `utils.file_lock()` context manager
- Symlink swaps are atomic: create temp symlink, then `os.replace`
- Config/state corruption → regenerate from filesystem (scan profile dirs)

### Error handling

- Custom exception hierarchy rooted at `SwitcherError` (see `switcher/errors.py`)
- User-facing output goes to stdout via `ui.py`; logs go to `~/.config/cli-switcher/logs/switcher.log`
- Graceful degradation: keyring failure → file fallback; quota API failure → skip pre-check; health check failure → status `unknown`

### Critical file paths to know

| Path | Purpose |
|------|---------|
| `~/.gemini/oauth_creds.json` | Gemini OAuth credentials (symlinked by switcher) |
| `~/.gemini/mcp-oauth-tokens.json` | Gemini token cache (**must delete on switch**) |
| `~/.gemini/settings.json` | Gemini hooks registered here |
| `~/.codex/auth.json` | Codex credentials (symlinked by switcher) |
| `~/.config/cli-switcher/config.toml` | Switcher user preferences |
| `~/.config/cli-switcher/state.json` | Active profiles, rotation state |
| `~/.config/cli-switcher/env.sh` | Exported API key env vars |

### Testing

Tests live in `tests/` mirroring the `switcher/` package structure. Uses `pytest` with `pytest-cov`.

```bash
# Run full suite
pytest

# Run a single test file
pytest tests/test_config.py -v

# Run a specific test function
pytest tests/test_config.py::test_load_config_defaults -v

# With coverage
pytest --cov=switcher --cov-report=term-missing
```

**Fixture conventions** (in `tests/conftest.py`):
- `tmp_config_dir` — temporary XDG config directory, avoids touching real `~/.config/cli-switcher/`
- `mock_keyring` — patches `keyring` module to use an in-memory dict backend
- `fake_gemini_dir` / `fake_codex_dir` — temporary directories mimicking `~/.gemini/` and `~/.codex/` structure with sample credential files
- `sample_oauth_creds` / `sample_auth_json` — fixture dicts matching real credential formats

**Mock patterns**:
- Never touch real `~/.gemini/`, `~/.codex/`, or OS keyring in tests — always use `tmp_path` and `mock_keyring`
- Patch `switcher.utils.get_config_dir()`, `get_gemini_dir()`, `get_codex_dir()` to return temp paths
- HTTP calls (health checks, quota API) use `unittest.mock.patch` on `requests.post`/`requests.get`
- Hook tests feed sample JSON to stdin and assert stdout JSON output

**Coverage target**: ≥80% line coverage. Hooks (`switcher/hooks/`) are standalone scripts — test them by invoking as subprocesses with mocked stdin/stdout.

### Env var precedence (important for switching)

- `GEMINI_API_KEY` overrides file-based auth in Gemini CLI
- `OPENAI_API_KEY` overrides file-based auth in Codex CLI
- Both `GOOGLE_API_KEY` and `GEMINI_API_KEY` should be set together (treated as aliases)
