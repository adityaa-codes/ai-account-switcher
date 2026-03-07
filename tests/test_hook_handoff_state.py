"""Tests for the quota-error handoff flag functions in state.py."""

from __future__ import annotations

import json
import time
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

if TYPE_CHECKING:
    from pathlib import Path

from switcher.state import (
    clear_quota_error_flag,
    get_quota_error_flag,
    set_quota_error_flag,
)


@pytest.fixture()
def tmp_config(tmp_path: Path) -> Path:
    """Return a temporary config dir, patched into switcher.state."""
    with patch("switcher.state.get_config_dir", return_value=tmp_path):
        yield tmp_path


# ---------------------------------------------------------------------------
# set_quota_error_flag
# ---------------------------------------------------------------------------


def test_set_creates_flag_file(tmp_config: Path) -> None:
    set_quota_error_flag("gemini")
    flag = tmp_config / "state" / "quota_error_gemini.json"
    assert flag.exists()


def test_set_writes_valid_json(tmp_config: Path) -> None:
    set_quota_error_flag("gemini")
    flag = tmp_config / "state" / "quota_error_gemini.json"
    data = json.loads(flag.read_text())
    assert "timestamp" in data
    assert "ttl" in data


def test_set_uses_custom_ttl(tmp_config: Path) -> None:
    set_quota_error_flag("gemini", ttl=60)
    flag = tmp_config / "state" / "quota_error_gemini.json"
    data = json.loads(flag.read_text())
    assert data["ttl"] == 60


def test_set_creates_parent_dirs(tmp_config: Path) -> None:
    state_dir = tmp_config / "state"
    assert not state_dir.exists()
    set_quota_error_flag("codex")
    assert state_dir.is_dir()


# ---------------------------------------------------------------------------
# get_quota_error_flag
# ---------------------------------------------------------------------------


def test_get_returns_false_when_no_file(tmp_config: Path) -> None:
    assert get_quota_error_flag("gemini") is False


def test_get_returns_true_after_set(tmp_config: Path) -> None:
    set_quota_error_flag("gemini")
    assert get_quota_error_flag("gemini") is True


def test_get_returns_false_after_ttl_expired(tmp_config: Path) -> None:
    set_quota_error_flag("gemini", ttl=1)
    # Mock time so the flag looks expired
    with patch("switcher.state.time") as mock_time:
        mock_time.time.return_value = time.time() + 200  # 200s later
        assert get_quota_error_flag("gemini") is False


def test_get_returns_false_for_corrupt_file(tmp_config: Path) -> None:
    flag = tmp_config / "state" / "quota_error_gemini.json"
    flag.parent.mkdir(parents=True, exist_ok=True)
    flag.write_text("not valid json", encoding="utf-8")
    assert get_quota_error_flag("gemini") is False


def test_get_returns_false_for_empty_file(tmp_config: Path) -> None:
    flag = tmp_config / "state" / "quota_error_gemini.json"
    flag.parent.mkdir(parents=True, exist_ok=True)
    flag.write_text("{}", encoding="utf-8")
    # Missing timestamp defaults to 0, so age will be very large → expired
    assert get_quota_error_flag("gemini") is False


def test_get_independent_per_cli(tmp_config: Path) -> None:
    set_quota_error_flag("gemini")
    assert get_quota_error_flag("codex") is False


# ---------------------------------------------------------------------------
# clear_quota_error_flag
# ---------------------------------------------------------------------------


def test_clear_removes_flag_file(tmp_config: Path) -> None:
    set_quota_error_flag("gemini")
    assert get_quota_error_flag("gemini") is True
    clear_quota_error_flag("gemini")
    assert get_quota_error_flag("gemini") is False


def test_clear_is_idempotent(tmp_config: Path) -> None:
    # Should not raise even if file doesn't exist
    clear_quota_error_flag("gemini")
    clear_quota_error_flag("gemini")


def test_clear_only_removes_target_cli(tmp_config: Path) -> None:
    set_quota_error_flag("gemini")
    set_quota_error_flag("codex")
    clear_quota_error_flag("gemini")
    assert get_quota_error_flag("gemini") is False
    assert get_quota_error_flag("codex") is True
