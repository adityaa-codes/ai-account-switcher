"""TOML configuration management for cli-switcher."""

from __future__ import annotations

import copy
import sys
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path

import tomli_w

from switcher.errors import ConfigError
from switcher.utils import file_lock, get_config_dir

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib  # type: ignore[import-not-found]

DEFAULT_CONFIG: dict[str, Any] = {
    "general": {
        "default_cli": "gemini",
        "storage_mode": "auto",
        "log_level": "info",
    },
    "auto_rotate": {
        "enabled": False,
        "pre_check": True,
        "strategy": "gemini3-first",
        "model_pattern": "gemini-3.*",
        "threshold_percent": 10,
        "max_retries": 3,
        "cache_minutes": 3,
        "restart_on_switch": False,
        "codex": {
            "enabled": False,
        },
    },
}


def _config_path() -> Path:
    return get_config_dir() / "config.toml"


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge override into base, returning a new dict."""
    result = copy.deepcopy(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def load_config() -> dict[str, Any]:
    """Read config.toml and merge with defaults.

    Returns:
        Complete config dict with defaults filled in for missing keys.
    """
    path = _config_path()
    if not path.exists():
        return copy.deepcopy(DEFAULT_CONFIG)
    try:
        with path.open("rb") as f:
            user_config = tomllib.load(f)
    except Exception as exc:
        raise ConfigError(f"Failed to parse {path}: {exc}") from exc
    return _deep_merge(DEFAULT_CONFIG, user_config)


def save_config(config: dict[str, Any]) -> None:
    """Write config dict to config.toml atomically.

    Args:
        config: Full config dict to persist.
    """
    path = _config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with file_lock(path):
        tmp = path.with_suffix(".toml.tmp")
        with tmp.open("wb") as f:
            tomli_w.dump(config, f)
        tmp.replace(path)


def get_config_value(key: str) -> Any:
    """Get a config value using dot-notation.

    Args:
        key: Dot-separated key path, e.g. 'auto_rotate.threshold_percent'.

    Returns:
        The config value at the given path.

    Raises:
        ConfigError: If the key path does not exist.
    """
    config = load_config()
    parts = key.split(".")
    current: Any = config
    for part in parts:
        if not isinstance(current, dict) or part not in current:
            raise ConfigError(f"Unknown config key: {key}")
        current = current[part]
    return current


def set_config_value(key: str, value: Any) -> None:
    """Set a config value using dot-notation with type coercion.

    Args:
        key: Dot-separated key path.
        value: New value (will be coerced to match the default's type).
    """
    config = load_config()
    parts = key.split(".")

    # Walk to the parent container
    current: Any = config
    for part in parts[:-1]:
        if not isinstance(current, dict) or part not in current:
            raise ConfigError(f"Unknown config key: {key}")
        current = current[part]

    final_key = parts[-1]
    if not isinstance(current, dict):
        raise ConfigError(f"Unknown config key: {key}")

    # Type coercion based on default value type
    default = _get_default_value(key)
    if default is not None:
        value = _coerce_type(value, type(default))

    current[final_key] = value
    save_config(config)


def _get_default_value(key: str) -> Any:
    """Look up the default value for a dot-notation key."""
    current: Any = DEFAULT_CONFIG
    for part in key.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def _coerce_type(value: Any, target_type: type) -> Any:
    """Coerce a string value to the target type."""
    if isinstance(value, target_type):
        return value
    if isinstance(value, str):
        if target_type is bool:
            return value.lower() in ("true", "1", "yes")
        if target_type is int:
            return int(value)
        if target_type is float:
            return float(value)
    return value
