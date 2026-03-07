"""Active profile state management (state.json)."""

from __future__ import annotations

import contextlib
import json
import time
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from switcher.utils import file_lock, get_config_dir

if TYPE_CHECKING:
    from pathlib import Path

DEFAULT_CLI_STATE: dict[str, Any] = {
    "active_profile": None,
    "rotation_index": 0,
    "retry_count": 0,
    "last_switch": None,
    "last_error": None,
}


def _state_path() -> Path:
    return get_config_dir() / "state.json"


def load_state() -> dict[str, Any]:
    """Read state.json with file lock.

    Returns:
        State dict with 'gemini' and 'codex' keys.
    """
    path = _state_path()
    if not path.exists():
        return {"gemini": dict(DEFAULT_CLI_STATE), "codex": dict(DEFAULT_CLI_STATE)}

    with file_lock(path), path.open("r", encoding="utf-8") as f:
        state: dict[str, Any] = json.load(f)

    # Ensure both CLI keys exist with defaults
    for cli in ("gemini", "codex"):
        if cli not in state:
            state[cli] = dict(DEFAULT_CLI_STATE)
        else:
            for key, default in DEFAULT_CLI_STATE.items():
                state[cli].setdefault(key, default)
    return state


def save_state(state: dict[str, Any]) -> None:
    """Write state.json with file lock.

    Args:
        state: Full state dict to persist.
    """
    path = _state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with file_lock(path):
        tmp = path.with_suffix(".json.tmp")
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
            f.write("\n")
        tmp.replace(path)


def get_active_profile(cli_name: str) -> str | None:
    """Return the active profile label for a CLI.

    Args:
        cli_name: 'gemini' or 'codex'.

    Returns:
        Profile label string, or None if no profile is active.
    """
    state = load_state()
    result: str | None = state.get(cli_name, {}).get("active_profile")
    return result


def set_active_profile(cli_name: str, label: str) -> None:
    """Set the active profile and update the timestamp.

    Args:
        cli_name: 'gemini' or 'codex'.
        label: Profile label to set as active.
    """
    state = load_state()
    if cli_name not in state:
        state[cli_name] = dict(DEFAULT_CLI_STATE)
    state[cli_name]["active_profile"] = label
    state[cli_name]["last_switch"] = datetime.now(timezone.utc).isoformat()
    save_state(state)


def get_rotation_state(cli_name: str) -> dict[str, Any]:
    """Return rotation state for a CLI.

    Args:
        cli_name: 'gemini' or 'codex'.

    Returns:
        Dict with 'retry_count', 'rotation_index', and 'last_error'.
    """
    state = load_state()
    cli_state = state.get(cli_name, DEFAULT_CLI_STATE)
    return {
        "retry_count": cli_state.get("retry_count", 0),
        "rotation_index": cli_state.get("rotation_index", 0),
        "last_error": cli_state.get("last_error"),
    }


def update_rotation_state(cli_name: str, **kwargs: Any) -> None:
    """Update rotation state fields for a CLI.

    Args:
        cli_name: 'gemini' or 'codex'.
        **kwargs: Fields to update (retry_count, rotation_index, last_error).
    """
    state = load_state()
    if cli_name not in state:
        state[cli_name] = dict(DEFAULT_CLI_STATE)
    for key, value in kwargs.items():
        if key in DEFAULT_CLI_STATE:
            state[cli_name][key] = value
    save_state(state)


# ---------------------------------------------------------------------------
# Crash-safe hook handoff state
# ---------------------------------------------------------------------------

_HANDOFF_TTL = 120  # seconds a quota-error flag stays valid


def _handoff_path(cli_name: str) -> Path:
    return get_config_dir() / "state" / f"quota_error_{cli_name}.json"


def set_quota_error_flag(cli_name: str, ttl: int = _HANDOFF_TTL) -> None:
    """Write a timestamped flag indicating a quota error occurred.

    Called by the AfterAgent hook so BeforeAgent can detect a recent switch
    without making a fresh API call.

    Args:
        cli_name: 'gemini' or 'codex'.
        ttl: Seconds before the flag is considered stale (default 120).
    """
    path = _handoff_path(cli_name)
    path.parent.mkdir(parents=True, exist_ok=True)
    with file_lock(path):
        path.write_text(
            json.dumps({"timestamp": time.time(), "ttl": ttl}) + "\n",
            encoding="utf-8",
        )


def get_quota_error_flag(cli_name: str) -> bool:
    """Return True if a non-expired quota-error flag exists for *cli_name*.

    Args:
        cli_name: 'gemini' or 'codex'.

    Returns:
        True if a valid (non-expired) flag is present, False otherwise.
    """
    path = _handoff_path(cli_name)
    if not path.exists():
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        age = time.time() - float(data.get("timestamp", 0))
        ttl = float(data.get("ttl", _HANDOFF_TTL))
        return age < ttl
    except (json.JSONDecodeError, ValueError, KeyError):
        return False


def clear_quota_error_flag(cli_name: str) -> None:
    """Delete the quota-error handoff flag for *cli_name*.

    Args:
        cli_name: 'gemini' or 'codex'.
    """
    path = _handoff_path(cli_name)
    with contextlib.suppress(OSError):
        path.unlink(missing_ok=True)
