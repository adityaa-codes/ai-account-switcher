# Gemini CLI Switcher Context

## Project Overview

**CLI Switcher** is a unified multi-account manager for the **Google Gemini CLI** and **OpenAI Codex CLI** on Linux. It enables developers to seamlessly switch between personal, work, and test accounts without manual re-authentication or configuration editing.

**Key Features:**
- **Instant Switching:** Atomic symlink swaps and environment variable injection allow switching without restarting the shell.
- **Unified Management:** Manages both Gemini and Codex profiles from a single CLI tool (`switcher`).
- **Auto-Rotation (Gemini):** Optional hooks to automatically rotate profiles upon quota exhaustion.
- **Security:** Integrates with Linux keyrings (GNOME Keyring/KWallet) for secure credential storage, with file fallback for headless systems.
- **Health Checks:** Validates OAuth tokens and API keys to ensure profiles are active before switching.

## Architecture & Tech Stack

- **Language:** Python 3.10+
- **Entry Point:** `main.py` (wraps `switcher.cli:main`)
- **CLI Framework:** `argparse` (standard library, no external CLI frameworks)
- **Configuration:** TOML (`pyproject.toml` for project, `config.toml` for user config)
- **State Management:** JSON with file locking (`fcntl`) to ensure concurrency safety.
- **Paths:** Strictly adheres to XDG Base Directory specification (`~/.config/cli-switcher/`).

## Building & Running

### Installation

1.  **Environment Setup:**
    ```bash
    python3 -m venv .venv
    source .venv/bin/activate
    ```

2.  **Install Editable:**
    ```bash
    pip install -e ".[dev]"
    ```

3.  **Install Shell Integration:**
    ```bash
    switcher install
    source ~/.bashrc  # or ~/.zshrc
    ```

### Running

- **Dashboard:** `switcher`
- **List Profiles:** `switcher gemini list` or `switcher codex list`
- **Switch Profile:** `switcher gemini switch <label>`
- **Run Health Checks:** `switcher gemini health`

### Testing

- **Run All Tests:**
    ```bash
    pytest
    ```
- **Run Specific Test:**
    ```bash
    pytest tests/test_config.py
    ```
- **With Coverage:**
    ```bash
    pytest --cov=switcher --cov-report=term-missing
    ```

### Linting & Formatting

The project uses `ruff` for both linting and formatting, and `mypy` for static type checking.

- **Check Linting:** `ruff check switcher/ tests/`
- **Fix Linting:** `ruff check --fix switcher/ tests/`
- **Format Code:** `ruff format switcher/ tests/`
- **Type Check:** `mypy switcher/`

## Development Conventions

- **Python Version:** Target Python 3.10+. Always use `from __future__ import annotations`.
- **Typing:** **Strict typing is mandatory.** All public functions must have type hints. Use `mypy --strict`.
- **Path Handling:** Always use `pathlib.Path`. Never use string manipulation for paths.
- **Docstrings:** Use **Google-style** docstrings (`Args:`, `Returns:`, `Raises:`).
- **Error Handling:** Use custom exceptions from `switcher.errors` (e.g., `SwitcherError`, `ProfileNotFoundError`). Avoid bare `except:` blocks.
- **File Safety:**
    - Use `switcher.utils.file_lock` context manager for all writes to shared state files (`state.json`, `config.toml`).
    - Use `switcher.utils.atomic_symlink` for profile switching.
- **Testing:**
    - **Isolation:** Tests must **NEVER** touch real user configuration (`~/.gemini`, `~/.codex`) or the system keyring.
    - **Fixtures:** Use `tmp_path` and `mock_keyring` fixtures to isolate filesystem and credential operations.

## Key Files & Directories

- **`main.py`**: CLI entry point.
- **`switcher/cli.py`**: Command routing and argument parsing.
- **`switcher/profiles/`**: Logic for managing profile directories and metadata.
- **`switcher/auth/`**: Handlers for OAuth, API keys, and Keyring interactions.
- **`switcher/hooks/`**: Standalone scripts used by Gemini CLI for auto-rotation.
- **`docs/spec.md`**: Definitive technical specification and architecture guide.
