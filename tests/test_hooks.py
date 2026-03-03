"""Tests for Gemini AfterAgent and BeforeAgent hook scripts."""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from switcher.hooks.gemini_after_agent import (
    QUOTA_ERROR_PATTERNS,
    is_quota_error,
)
from switcher.hooks.gemini_before_agent import (
    _load_quota_cache,
    _save_quota_cache,
    _should_switch,
)

# ---------------------------------------------------------------------------
# is_quota_error
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "response",
    [
        "Error 429: Too Many Requests",
        "Resource exhausted for this project",
        "Quota exceeded for the day",
        "Usage limit reached for all Gemini models",
        "limit reached for all available models",
        "RESOURCE_EXHAUSTED error occurred",
        "rate limit hit",
        "Rate Limit Reached",
    ],
)
def test_is_quota_error_returns_true(response: str) -> None:
    assert is_quota_error(response) is True


@pytest.mark.parametrize(
    "response",
    [
        "Success: response generated",
        "Error 500: Internal server error",
        "Model not found",
        "",
        "All good, no issues",
    ],
)
def test_is_quota_error_returns_false(response: str) -> None:
    assert is_quota_error(response) is False


def test_quota_error_patterns_are_compiled() -> None:
    import re

    for pattern in QUOTA_ERROR_PATTERNS:
        assert isinstance(pattern, re.Pattern)


# ---------------------------------------------------------------------------
# _should_switch
# ---------------------------------------------------------------------------


def test_should_switch_empty_quotas_returns_false() -> None:
    assert _should_switch({}, 0.1, "conservative") is False


def test_should_switch_conservative_all_below() -> None:
    quotas = {"gemini-pro": 0.05, "gemini-flash": 0.03}
    assert _should_switch(quotas, 0.1, "conservative") is True


def test_should_switch_conservative_one_above() -> None:
    quotas = {"gemini-pro": 0.05, "gemini-flash": 0.5}
    assert _should_switch(quotas, 0.1, "conservative") is False


def test_should_switch_gemini3_first_any_below() -> None:
    quotas = {"gemini-pro": 0.05, "gemini-flash": 0.9}
    assert _should_switch(quotas, 0.1, "gemini3-first") is True


def test_should_switch_gemini3_first_all_above() -> None:
    quotas = {"gemini-pro": 0.5, "gemini-flash": 0.9}
    assert _should_switch(quotas, 0.1, "gemini3-first") is False


# ---------------------------------------------------------------------------
# _load_quota_cache / _save_quota_cache
# ---------------------------------------------------------------------------


def test_save_and_load_quota_cache(tmp_path: Path) -> None:
    cache_file = tmp_path / "quota_gemini.json"
    quotas = {"gemini-pro": 0.5}
    _save_quota_cache(cache_file, quotas, ttl=300)
    loaded = _load_quota_cache(cache_file)
    assert loaded == quotas


def test_load_quota_cache_missing_returns_none(tmp_path: Path) -> None:
    cache_file = tmp_path / "nonexistent.json"
    assert _load_quota_cache(cache_file) is None


def test_load_quota_cache_expired_returns_none(tmp_path: Path) -> None:
    import time

    cache_file = tmp_path / "quota.json"
    old_data = {
        "cached_at": time.time() - 400,  # 400 seconds ago
        "ttl": 300,
        "quotas": {"gemini-pro": 0.5},
    }
    cache_file.write_text(json.dumps(old_data))
    assert _load_quota_cache(cache_file) is None


def test_load_quota_cache_corrupt_json_returns_none(tmp_path: Path) -> None:
    cache_file = tmp_path / "quota.json"
    cache_file.write_text("{bad json")
    assert _load_quota_cache(cache_file) is None


# ---------------------------------------------------------------------------
# after_agent.main() — invoked via subprocess stdin/stdout capture
# ---------------------------------------------------------------------------


def test_after_agent_no_quota_error_returns_empty(tmp_path: Path) -> None:
    from switcher.hooks import gemini_after_agent as mod

    config = {
        "auto_rotate": {
            "enabled": True,
            "max_retries": 3,
        }
    }
    rot = {"retry_count": 0, "last_error": None}
    stdin_data = {"prompt_response": "Success: everything is fine"}

    out_buf = io.StringIO()
    with (
        patch.object(
            sys, "stdin", io.TextIOWrapper(io.BytesIO(json.dumps(stdin_data).encode()))
        ),
        patch.object(sys, "stdout", out_buf),
        patch.object(mod, "_find_switcher", return_value="/fake/switcher"),
        patch.dict(
            sys.modules,
            {
                "switcher.config": MagicMock(
                    load_config=MagicMock(return_value=config)
                ),
                "switcher.state": MagicMock(
                    get_rotation_state=MagicMock(return_value=rot),
                    update_rotation_state=MagicMock(),
                    get_active_profile=MagicMock(return_value="work"),
                ),
            },
        ),
    ):
        mod.main()

    result = json.loads(out_buf.getvalue())
    assert result == {}


def test_after_agent_auto_rotate_disabled_returns_empty() -> None:
    from switcher.hooks import gemini_after_agent as mod

    config = {"auto_rotate": {"enabled": False, "max_retries": 3}}
    stdin_data = {"prompt_response": "Error 429: quota exceeded"}
    out_buf = io.StringIO()
    with (
        patch.object(
            sys, "stdin", io.TextIOWrapper(io.BytesIO(json.dumps(stdin_data).encode()))
        ),
        patch.object(sys, "stdout", out_buf),
        patch.dict(
            sys.modules,
            {
                "switcher.config": MagicMock(
                    load_config=MagicMock(return_value=config)
                ),
                "switcher.state": MagicMock(
                    get_rotation_state=MagicMock(return_value={"retry_count": 0}),
                    update_rotation_state=MagicMock(),
                    get_active_profile=MagicMock(return_value="work"),
                ),
            },
        ),
    ):
        mod.main()
    result = json.loads(out_buf.getvalue())
    assert result == {}


def test_after_agent_max_retries_reached_returns_empty() -> None:
    from switcher.hooks import gemini_after_agent as mod

    config = {"auto_rotate": {"enabled": True, "max_retries": 3}}
    rot = {"retry_count": 3, "last_error": None}
    stdin_data = {"prompt_response": "Error 429: quota exceeded"}
    out_buf = io.StringIO()
    with (
        patch.object(
            sys, "stdin", io.TextIOWrapper(io.BytesIO(json.dumps(stdin_data).encode()))
        ),
        patch.object(sys, "stdout", out_buf),
        patch.dict(
            sys.modules,
            {
                "switcher.config": MagicMock(
                    load_config=MagicMock(return_value=config)
                ),
                "switcher.state": MagicMock(
                    get_rotation_state=MagicMock(return_value=rot),
                    update_rotation_state=MagicMock(),
                    get_active_profile=MagicMock(return_value="work"),
                ),
            },
        ),
    ):
        mod.main()
    result = json.loads(out_buf.getvalue())
    assert result == {}


def test_after_agent_quota_error_with_rotation_returns_retry() -> None:
    from unittest.mock import MagicMock

    from switcher.hooks import gemini_after_agent as mod

    config = {"auto_rotate": {"enabled": True, "max_retries": 3}}
    rot = {"retry_count": 0, "last_error": None}
    stdin_data = {"prompt_response": "Error 429: quota exceeded"}
    mock_result = SimpleNamespace(returncode=0, stdout="", stderr="")

    out_buf = io.StringIO()
    with (
        patch.object(
            sys, "stdin", io.TextIOWrapper(io.BytesIO(json.dumps(stdin_data).encode()))
        ),
        patch.object(sys, "stdout", out_buf),
        patch.object(mod, "_find_switcher", return_value="/fake/switcher"),
        patch("subprocess.run", return_value=mock_result),
        patch.dict(
            sys.modules,
            {
                "switcher.config": MagicMock(
                    load_config=MagicMock(return_value=config)
                ),
                "switcher.state": MagicMock(
                    get_rotation_state=MagicMock(return_value=rot),
                    update_rotation_state=MagicMock(),
                    get_active_profile=MagicMock(return_value="personal"),
                ),
            },
        ),
    ):
        mod.main()
    result = json.loads(out_buf.getvalue())
    assert result.get("decision") == "retry"
    assert "personal" in result.get("systemMessage", "")


def test_after_agent_exception_returns_empty() -> None:
    from switcher.hooks import gemini_after_agent as mod

    # Pass invalid JSON to trigger exception
    out_buf = io.StringIO()
    with (
        patch.object(sys, "stdin", io.TextIOWrapper(io.BytesIO(b"NOT JSON"))),
        patch.object(sys, "stdout", out_buf),
    ):
        mod.main()
    result = json.loads(out_buf.getvalue())
    assert result == {}


# ---------------------------------------------------------------------------
# before_agent.main() — minimal coverage
# ---------------------------------------------------------------------------


def test_before_agent_exception_returns_empty() -> None:
    from switcher.hooks import gemini_before_agent as mod

    out_buf = io.StringIO()
    with (
        patch.object(sys, "stdin", io.TextIOWrapper(io.BytesIO(b"NOT JSON"))),
        patch.object(sys, "stdout", out_buf),
    ):
        mod.main()
    result = json.loads(out_buf.getvalue())
    assert result == {}


def test_before_agent_disabled_returns_empty() -> None:
    from switcher.hooks import gemini_before_agent as mod

    config = {
        "auto_rotate": {
            "enabled": False,
            "pre_check": True,
            "threshold_percent": 10,
            "strategy": "conservative",
            "cache_minutes": 5,
        }
    }
    stdin_data = {}
    out_buf = io.StringIO()
    with (
        patch.object(
            sys, "stdin", io.TextIOWrapper(io.BytesIO(json.dumps(stdin_data).encode()))
        ),
        patch.object(sys, "stdout", out_buf),
        patch.dict(
            sys.modules,
            {
                "switcher.config": MagicMock(
                    load_config=MagicMock(return_value=config)
                ),
                "switcher.state": MagicMock(
                    get_active_profile=MagicMock(return_value="work")
                ),
                "switcher.utils": MagicMock(
                    get_config_dir=MagicMock(return_value=Path("/tmp"))
                ),
            },
        ),
    ):
        mod.main()
    result = json.loads(out_buf.getvalue())
    assert result == {}


def test_before_agent_no_active_profile_returns_empty() -> None:
    from switcher.hooks import gemini_before_agent as mod

    config = {
        "auto_rotate": {
            "enabled": True,
            "pre_check": True,
            "threshold_percent": 10,
            "strategy": "conservative",
            "cache_minutes": 5,
        }
    }
    stdin_data = {}
    out_buf = io.StringIO()
    with (
        patch.object(
            sys, "stdin", io.TextIOWrapper(io.BytesIO(json.dumps(stdin_data).encode()))
        ),
        patch.object(sys, "stdout", out_buf),
        patch.dict(
            sys.modules,
            {
                "switcher.config": MagicMock(
                    load_config=MagicMock(return_value=config)
                ),
                "switcher.state": MagicMock(
                    get_active_profile=MagicMock(return_value=None)
                ),
                "switcher.utils": MagicMock(
                    get_config_dir=MagicMock(return_value=Path("/tmp"))
                ),
            },
        ),
    ):
        mod.main()
    result = json.loads(out_buf.getvalue())
    assert result == {}
