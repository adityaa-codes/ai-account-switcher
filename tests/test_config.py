"""Tests for TOML config management."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from switcher.config import (
    DEFAULT_CONFIG,
    get_config_value,
    load_config,
    save_config,
    set_config_value,
)
from switcher.errors import ConfigError

if TYPE_CHECKING:
    from pathlib import Path


def test_load_config_returns_defaults_when_file_missing(tmp_config_dir: Path) -> None:
    config = load_config()
    assert config["general"]["storage_mode"] == "auto"
    assert config["auto_rotate"]["enabled"] is False
    assert config["auto_rotate"]["threshold_percent"] == 10
    assert config["auto_rotate"]["pre_check"] is True


def test_load_config_merges_partial_toml(tmp_config_dir: Path) -> None:
    from switcher.utils import get_config_dir

    config_path = get_config_dir() / "config.toml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text("[auto_rotate]\nenabled = true\n", encoding="utf-8")

    config = load_config()
    assert config["auto_rotate"]["enabled"] is True
    # Other keys should still have defaults
    assert config["auto_rotate"]["threshold_percent"] == 10
    assert config["general"]["log_level"] == "info"


def test_load_config_raises_on_corrupt_toml(tmp_config_dir: Path) -> None:
    from switcher.utils import get_config_dir

    config_path = get_config_dir() / "config.toml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text("[[[[invalid toml", encoding="utf-8")

    with pytest.raises(ConfigError, match="Failed to parse"):
        load_config()


def test_get_config_value_dot_notation(tmp_config_dir: Path) -> None:
    val = get_config_value("auto_rotate.threshold_percent")
    assert val == 10


def test_get_config_value_top_level_section(tmp_config_dir: Path) -> None:
    val = get_config_value("general.storage_mode")
    assert val == "auto"


def test_get_config_value_unknown_key_raises(tmp_config_dir: Path) -> None:
    with pytest.raises(ConfigError, match="Unknown config key"):
        get_config_value("auto_rotate.nonexistent")


def test_set_config_value_persists(tmp_config_dir: Path) -> None:
    set_config_value("auto_rotate.enabled", "true")
    val = get_config_value("auto_rotate.enabled")
    assert val is True


def test_set_config_value_bool_coercion(tmp_config_dir: Path) -> None:
    set_config_value("auto_rotate.enabled", "true")
    assert get_config_value("auto_rotate.enabled") is True
    set_config_value("auto_rotate.enabled", "false")
    assert get_config_value("auto_rotate.enabled") is False


def test_set_config_value_int_coercion(tmp_config_dir: Path) -> None:
    set_config_value("auto_rotate.threshold_percent", "25")
    assert get_config_value("auto_rotate.threshold_percent") == 25


def test_set_config_value_unknown_parent_raises(tmp_config_dir: Path) -> None:
    with pytest.raises(ConfigError, match="Unknown config key"):
        set_config_value("nonexistent_section.key", "x")


def test_save_and_reload_roundtrip(tmp_config_dir: Path) -> None:
    import copy

    cfg: dict[str, Any] = copy.deepcopy(DEFAULT_CONFIG)
    cfg["auto_rotate"]["max_retries"] = 7
    save_config(cfg)

    reloaded = load_config()
    assert reloaded["auto_rotate"]["max_retries"] == 7


def test_default_config_has_pre_check() -> None:
    assert "pre_check" in DEFAULT_CONFIG["auto_rotate"]
    assert DEFAULT_CONFIG["auto_rotate"]["pre_check"] is True
