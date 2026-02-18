# Repository Guidelines

## Project Structure & Module Organization
Core code lives in `switcher/`, organized by responsibility:
- `cli.py` is the command entrypoint (`switcher` script).
- `profiles/` manages Gemini/Codex profile lifecycle.
- `auth/` handles credential activation and keyring integration.
- `hooks/` contains Gemini before/after-agent automation.
- `config.py`, `state.py`, `health.py`, and `installer.py` cover config, runtime state, checks, and shell integration.

Supporting files:
- `main.py`: direct-run entry script.
- `docs/spec.md`: technical spec.
- `tests/`: pytest suite (currently minimal; expand with new work).

## Build, Test, and Development Commands
Set up and develop locally:
- `python3 -m venv .venv && source .venv/bin/activate`
- `pip install -e ".[dev]"` installs editable package with dev tools.
- `switcher version` verifies CLI wiring.

Quality checks:
- `pytest` runs tests.
- `pytest --cov=switcher --cov-report=term-missing` checks coverage.
- `ruff check switcher/ tests/` runs lint rules.
- `ruff format --check switcher/ tests/` enforces formatting.
- `mypy switcher/` runs strict static typing.

## Coding Style & Naming Conventions
- Target Python 3.10+ with type hints on all public functions.
- Ruff is the formatter/linter; max line length is 88, double quotes preferred.
- Keep modules focused; place provider-specific logic under `switcher/profiles/` or `switcher/auth/`.
- Use `snake_case` for functions/modules, `PascalCase` for classes, and clear verb-first CLI actions.

## Testing Guidelines
- Add tests under `tests/` as `test_<feature>.py`.
- Isolate filesystem and credential effects using `tmp_path` and mocks; do not use real `~/.gemini`, `~/.codex`, or OS keyring data.
- Mock network calls (`requests`) in health/quota flows.
- Aim for at least 80% line coverage for touched areas.

## Commit & Pull Request Guidelines
Git history follows Conventional Commit style (`feat:`, `docs:`, `build:`, `chore:`). Keep messages imperative and scoped, for example: `feat: add codex profile export`.

For PRs:
- Keep commits atomic and logically grouped.
- Run `ruff check && ruff format --check && mypy switcher/ && pytest` before opening.
- Include a concise description, linked issue(s), and terminal output/screenshots when behavior or UX changes.
