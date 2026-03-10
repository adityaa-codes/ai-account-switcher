"""Tests for active profile state management."""

from __future__ import annotations

from typing import TYPE_CHECKING

from switcher.state import (
    get_active_profile,
    get_rotation_state,
    load_state,
    save_state,
    set_active_profile,
    update_rotation_state,
)

if TYPE_CHECKING:
    from pathlib import Path


def test_load_state_returns_defaults_when_file_missing(tmp_config_dir: Path) -> None:
    state = load_state()
    assert "gemini" in state
    assert "codex" in state
    assert state["gemini"]["active_profile"] is None
    assert state["gemini"]["retry_count"] == 0
    assert state["codex"]["active_profile"] is None


def test_set_and_get_active_profile_roundtrip(tmp_config_dir: Path) -> None:
    set_active_profile("gemini", "work@example.com")
    assert get_active_profile("gemini") == "work@example.com"


def test_set_active_profile_does_not_affect_other_cli(tmp_config_dir: Path) -> None:
    set_active_profile("gemini", "gemini-work")
    assert get_active_profile("codex") is None


def test_set_active_profile_updates_last_switch(tmp_config_dir: Path) -> None:
    set_active_profile("gemini", "personal")
    state = load_state()
    assert state["gemini"]["last_switch"] is not None


def test_load_state_fills_missing_cli_keys(tmp_config_dir: Path) -> None:
    from switcher.utils import get_config_dir

    state_path = get_config_dir() / "state.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    # Write state with only gemini key
    import json

    state_path.write_text(
        json.dumps({"gemini": {"active_profile": "personal", "retry_count": 0}}),
        encoding="utf-8",
    )
    state = load_state()
    # codex should be filled in with defaults
    assert "codex" in state
    assert state["codex"]["active_profile"] is None
    assert state["gemini"]["active_profile"] == "personal"


def test_update_rotation_state_persists(tmp_config_dir: Path) -> None:
    update_rotation_state("gemini", retry_count=3, last_error="quota exceeded")
    rot = get_rotation_state("gemini")
    assert rot["retry_count"] == 3
    assert rot["last_error"] == "quota exceeded"


def test_update_rotation_state_ignores_unknown_keys(tmp_config_dir: Path) -> None:
    # Should not raise; unknown keys are silently dropped
    update_rotation_state("gemini", unknown_key="value")
    state = load_state()
    assert "unknown_key" not in state["gemini"]


def test_get_rotation_state_returns_defaults_when_missing(
    tmp_config_dir: Path,
) -> None:
    rot = get_rotation_state("gemini")
    assert rot["retry_count"] == 0
    assert rot["rotation_index"] == 0
    assert rot["last_error"] is None


def test_save_and_load_state_roundtrip(tmp_config_dir: Path) -> None:
    state = load_state()
    state["gemini"]["active_profile"] = "roundtrip@example.com"
    state["gemini"]["retry_count"] = 2
    save_state(state)

    reloaded = load_state()
    assert reloaded["gemini"]["active_profile"] == "roundtrip@example.com"
    assert reloaded["gemini"]["retry_count"] == 2


# ── Phase 2: C-3 OAuth client cache ────────────────────────────────────────


def test_cache_oauth_client_writes_and_reads(tmp_config_dir: Path) -> None:
    """C-3: cache_oauth_client writes, get_cached_oauth_client returns it."""
    from switcher.state import cache_oauth_client, get_cached_oauth_client

    cache_oauth_client(("my_id", "my_secret"))
    result = get_cached_oauth_client()
    assert result == ("my_id", "my_secret"), f"Expected cached client, got {result!r}"


def test_get_cached_oauth_client_returns_none_when_missing(
    tmp_config_dir: Path,
) -> None:
    """C-3: get_cached_oauth_client returns None when cache file absent."""
    from switcher.state import get_cached_oauth_client

    result = get_cached_oauth_client()
    assert result is None


def test_get_cached_oauth_client_expired_returns_none(tmp_config_dir: Path) -> None:
    """C-3: get_cached_oauth_client returns None when cache is older than 24 hours."""
    import json
    import time

    from switcher.state import (
        _OAUTH_CLIENT_CACHE_TTL,
        _oauth_cache_path,
        cache_oauth_client,
        get_cached_oauth_client,
    )

    cache_oauth_client(("old_id", "old_sec"))
    # Overwrite cached_at with an expired timestamp
    path = _oauth_cache_path()
    data = json.loads(path.read_text())
    data["cached_at"] = time.time() - (_OAUTH_CLIENT_CACHE_TTL + 1)
    path.write_text(json.dumps(data))

    result = get_cached_oauth_client()
    assert result is None, "Expired cache should return None"
