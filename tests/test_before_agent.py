"""Tests for switcher.hooks.gemini_before_agent.

Covers _get_access_token, _refresh_and_get_token, _fetch_quota, and
main() across all significant code paths: cache hit, cache miss, quota
above/below threshold, successful switch, failed switch, and error paths.
"""

from __future__ import annotations

import io
import json
import sys
from types import SimpleNamespace
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

if TYPE_CHECKING:
    from pathlib import Path

from switcher.hooks.gemini_before_agent import (
    _fetch_quota,
    _get_access_token,
    _refresh_and_get_token,
    _save_quota_cache,
    main,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_creds(profile_dir: Path, data: dict) -> None:  # type: ignore[type-arg]
    """Write oauth_creds.json into profile_dir."""
    profile_dir.mkdir(parents=True, exist_ok=True)
    (profile_dir / "oauth_creds.json").write_text(json.dumps(data))


def _run_main(
    stdin_data: dict,  # type: ignore[type-arg]
    config: dict,  # type: ignore[type-arg]
    active_profile: str | None,
    config_dir: Path,
    extra_patches: dict | None = None,  # type: ignore[type-arg]
) -> dict:  # type: ignore[type-arg]
    """Run main() with mocked stdio and switcher modules. Returns parsed stdout JSON."""
    stdin_bytes = json.dumps(stdin_data).encode()
    out_buf = io.StringIO()

    state_mock = MagicMock()
    state_mock.get_active_profile.return_value = active_profile

    utils_mock = MagicMock()
    utils_mock.get_config_dir.return_value = config_dir

    mods: dict[str, object] = {
        "switcher.config": MagicMock(load_config=MagicMock(return_value=config)),
        "switcher.state": state_mock,
        "switcher.utils": utils_mock,
    }
    if extra_patches:
        mods.update(extra_patches)

    with (
        patch.object(
            sys,
            "stdin",
            io.TextIOWrapper(io.BytesIO(stdin_bytes)),
        ),
        patch.object(sys, "stdout", out_buf),
        patch.dict(sys.modules, mods),
    ):
        main()

    return json.loads(out_buf.getvalue())  # type: ignore[no-any-return]


def _config(
    enabled: bool = True,
    pre_check: bool = True,
    threshold: int = 10,
    strategy: str = "conservative",
    cache_minutes: int = 5,
) -> dict:  # type: ignore[type-arg]
    return {
        "auto_rotate": {
            "enabled": enabled,
            "pre_check": pre_check,
            "threshold_percent": threshold,
            "strategy": strategy,
            "cache_minutes": cache_minutes,
        }
    }


# ---------------------------------------------------------------------------
# _get_access_token
# ---------------------------------------------------------------------------


def test_get_access_token_flat_format(tmp_path: Path) -> None:
    profile_dir = tmp_path / "profile"
    _write_creds(profile_dir, {"access_token": "flat-token-123"})

    result = _get_access_token(profile_dir)

    assert result == "flat-token-123"


def test_get_access_token_nested_format(tmp_path: Path) -> None:
    profile_dir = tmp_path / "profile"
    _write_creds(
        profile_dir,
        {"token": {"accessToken": "nested-token-456"}},
    )

    result = _get_access_token(profile_dir)

    assert result == "nested-token-456"


def test_get_access_token_missing_file_returns_none(tmp_path: Path) -> None:
    profile_dir = tmp_path / "profile"
    profile_dir.mkdir()

    assert _get_access_token(profile_dir) is None


def test_get_access_token_corrupt_json_returns_none(tmp_path: Path) -> None:
    profile_dir = tmp_path / "profile"
    profile_dir.mkdir()
    (profile_dir / "oauth_creds.json").write_text("{bad json!")

    assert _get_access_token(profile_dir) is None


def test_get_access_token_no_token_fields_returns_none(tmp_path: Path) -> None:
    profile_dir = tmp_path / "profile"
    _write_creds(profile_dir, {"other_field": "value"})

    assert _get_access_token(profile_dir) is None


def test_get_access_token_nested_missing_access_token_returns_empty(
    tmp_path: Path,
) -> None:
    """Nested token dict without accessToken key returns empty string (not None)."""
    profile_dir = tmp_path / "profile"
    _write_creds(profile_dir, {"token": {"refreshToken": "rt"}})

    result = _get_access_token(profile_dir)

    assert result == ""


# ---------------------------------------------------------------------------
# _refresh_and_get_token
# ---------------------------------------------------------------------------


def test_refresh_no_creds_file_returns_none(tmp_path: Path) -> None:
    profile_dir = tmp_path / "profile"
    profile_dir.mkdir()

    assert _refresh_and_get_token(profile_dir) is None


def test_refresh_no_refresh_token_falls_back_to_access_token(
    tmp_path: Path,
) -> None:
    """When there's no refresh_token, fall back to reading access_token directly."""
    profile_dir = tmp_path / "profile"
    _write_creds(profile_dir, {"access_token": "existing-access", "other": "data"})

    result = _refresh_and_get_token(profile_dir)

    assert result == "existing-access"


def test_refresh_flat_refresh_token_success(tmp_path: Path) -> None:
    profile_dir = tmp_path / "profile"
    _write_creds(
        profile_dir,
        {"refresh_token": "rt-abc", "access_token": "old-access"},
    )

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"access_token": "fresh-token"}

    mock_requests = MagicMock()
    mock_requests.post.return_value = mock_resp

    mock_health = MagicMock()
    mock_health._KNOWN_GOOGLE_OAUTH_CLIENTS = [("client-id", "client-secret")]

    with patch.dict(
        sys.modules,
        {
            "requests": mock_requests,
            "switcher.health": mock_health,
        },
    ):
        result = _refresh_and_get_token(profile_dir)

    assert result == "fresh-token"


def test_refresh_nested_refresh_token_success(tmp_path: Path) -> None:
    profile_dir = tmp_path / "profile"
    _write_creds(
        profile_dir,
        {"token": {"refreshToken": "rt-nested", "accessToken": "old"}},
    )

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"access_token": "fresh-nested"}

    mock_requests = MagicMock()
    mock_requests.post.return_value = mock_resp

    mock_health = MagicMock()
    mock_health._KNOWN_GOOGLE_OAUTH_CLIENTS = [("cid", "csecret")]

    with patch.dict(
        sys.modules,
        {
            "requests": mock_requests,
            "switcher.health": mock_health,
        },
    ):
        result = _refresh_and_get_token(profile_dir)

    assert result == "fresh-nested"


def test_refresh_all_clients_fail_falls_back_to_access_token(
    tmp_path: Path,
) -> None:
    """All OAuth clients fail (non-200) — falls back to the existing access_token."""
    profile_dir = tmp_path / "profile"
    _write_creds(
        profile_dir,
        {"refresh_token": "rt", "access_token": "fallback-token"},
    )

    mock_resp = MagicMock()
    mock_resp.status_code = 401

    mock_requests = MagicMock()
    mock_requests.post.return_value = mock_resp

    mock_health = MagicMock()
    mock_health._KNOWN_GOOGLE_OAUTH_CLIENTS = [
        ("cid1", "cs1"),
        ("cid2", "cs2"),
    ]

    with patch.dict(
        sys.modules,
        {
            "requests": mock_requests,
            "switcher.health": mock_health,
        },
    ):
        result = _refresh_and_get_token(profile_dir)

    assert result == "fallback-token"


def test_refresh_exception_in_request_falls_back(tmp_path: Path) -> None:
    profile_dir = tmp_path / "profile"
    _write_creds(
        profile_dir,
        {"refresh_token": "rt", "access_token": "fallback"},
    )

    mock_requests = MagicMock()
    mock_requests.post.side_effect = OSError("network unreachable")

    mock_health = MagicMock()
    mock_health._KNOWN_GOOGLE_OAUTH_CLIENTS = [("cid", "cs")]

    with patch.dict(
        sys.modules,
        {
            "requests": mock_requests,
            "switcher.health": mock_health,
        },
    ):
        result = _refresh_and_get_token(profile_dir)

    assert result == "fallback"


# ---------------------------------------------------------------------------
# _fetch_quota
# ---------------------------------------------------------------------------


def test_fetch_quota_success() -> None:
    project_resp = MagicMock()
    project_resp.status_code = 200
    project_resp.json.return_value = {"cloudaicompanionProject": "proj-123"}

    quota_resp = MagicMock()
    quota_resp.status_code = 200
    quota_resp.json.return_value = {
        "userQuota": [
            {"modelName": "gemini-pro", "remainingFraction": 0.75},
            {"modelName": "gemini-flash", "remainingFraction": 0.50},
        ]
    }

    mock_requests = MagicMock()
    mock_requests.post.side_effect = [project_resp, quota_resp]

    with patch.dict(sys.modules, {"requests": mock_requests}):
        result = _fetch_quota("my-access-token")

    assert result == {"gemini-pro": 0.75, "gemini-flash": 0.50}


def test_fetch_quota_step1_non200_returns_none() -> None:
    mock_resp = MagicMock()
    mock_resp.status_code = 403

    mock_requests = MagicMock()
    mock_requests.post.return_value = mock_resp

    with patch.dict(sys.modules, {"requests": mock_requests}):
        result = _fetch_quota("token")

    assert result is None


def test_fetch_quota_step1_no_project_id_returns_none() -> None:
    project_resp = MagicMock()
    project_resp.status_code = 200
    project_resp.json.return_value = {}  # no cloudaicompanionProject key

    mock_requests = MagicMock()
    mock_requests.post.return_value = project_resp

    with patch.dict(sys.modules, {"requests": mock_requests}):
        result = _fetch_quota("token")

    assert result is None


def test_fetch_quota_step2_non200_returns_none() -> None:
    project_resp = MagicMock()
    project_resp.status_code = 200
    project_resp.json.return_value = {"cloudaicompanionProject": "proj-123"}

    quota_resp = MagicMock()
    quota_resp.status_code = 429

    mock_requests = MagicMock()
    mock_requests.post.side_effect = [project_resp, quota_resp]

    with patch.dict(sys.modules, {"requests": mock_requests}):
        result = _fetch_quota("token")

    assert result is None


def test_fetch_quota_exception_returns_none() -> None:
    mock_requests = MagicMock()
    mock_requests.post.side_effect = OSError("connection refused")

    with patch.dict(sys.modules, {"requests": mock_requests}):
        result = _fetch_quota("token")

    assert result is None


def test_fetch_quota_uses_authorization_header() -> None:
    project_resp = MagicMock()
    project_resp.status_code = 200
    project_resp.json.return_value = {"cloudaicompanionProject": "p"}

    quota_resp = MagicMock()
    quota_resp.status_code = 200
    quota_resp.json.return_value = {"userQuota": []}

    mock_requests = MagicMock()
    mock_requests.post.side_effect = [project_resp, quota_resp]

    with patch.dict(sys.modules, {"requests": mock_requests}):
        _fetch_quota("bearer-xyz")

    first_call_kwargs = mock_requests.post.call_args_list[0][1]
    assert first_call_kwargs["headers"]["Authorization"] == "Bearer bearer-xyz"


# ---------------------------------------------------------------------------
# main() — disabled / pre_check off
# ---------------------------------------------------------------------------


def test_main_auto_rotate_disabled_returns_empty(tmp_path: Path) -> None:
    result = _run_main({}, _config(enabled=False), "work", tmp_path)
    assert result == {}


def test_main_pre_check_disabled_returns_empty(tmp_path: Path) -> None:
    result = _run_main({}, _config(pre_check=False), "work", tmp_path)
    assert result == {}


def test_main_no_active_profile_returns_empty(tmp_path: Path) -> None:
    result = _run_main({}, _config(), None, tmp_path)
    assert result == {}


def test_main_profile_dir_missing_returns_empty(tmp_path: Path) -> None:
    """Profile is set in state but directory doesn't exist on disk."""
    # Don't create the profile directory
    result = _run_main({}, _config(), "nonexistent-profile", tmp_path)
    assert result == {}


# ---------------------------------------------------------------------------
# main() — cache hit paths
# ---------------------------------------------------------------------------


def test_main_cache_hit_quota_above_threshold_returns_empty(tmp_path: Path) -> None:
    # Create profile directory
    profile_dir = (
        tmp_path / ".config" / "ai-account-switcher" / "profiles" / "gemini" / "work"
    )
    profile_dir.mkdir(parents=True)

    # Write a fresh cache with quota well above threshold (10%)
    cache_file = (
        tmp_path / ".config" / "ai-account-switcher" / "cache" / "quota_gemini.json"
    )
    _save_quota_cache(
        cache_file,
        {"gemini-pro": 0.80, "gemini-flash": 0.90},
        ttl=300,
    )

    config_dir = tmp_path / ".config" / "ai-account-switcher"

    result = _run_main({}, _config(threshold=10), "work", config_dir)
    assert result == {}


def test_main_cache_hit_quota_below_threshold_switch_succeeds(
    tmp_path: Path,
) -> None:
    """Quota below threshold: subprocess switch succeeds → return systemMessage."""
    config_dir = tmp_path / ".config" / "ai-account-switcher"
    profile_dir = config_dir / "profiles" / "gemini" / "work"
    profile_dir.mkdir(parents=True)

    cache_file = config_dir / "cache" / "quota_gemini.json"
    _save_quota_cache(cache_file, {"gemini-pro": 0.02}, ttl=300)

    mock_result = SimpleNamespace(returncode=0, stdout="", stderr="")
    after_agent_mock = MagicMock()
    after_agent_mock._find_switcher.return_value = "/fake/switcher"

    state_mock = MagicMock()
    # First call (get_active_profile in main) returns "work",
    # second call (new_profile after switch) returns "personal"
    state_mock.get_active_profile.side_effect = ["work", "personal"]

    utils_mock = MagicMock()
    utils_mock.get_config_dir.return_value = config_dir

    with (
        patch.object(sys, "stdin", io.TextIOWrapper(io.BytesIO(b"{}"))),
        patch.object(sys, "stdout", out_buf := io.StringIO()),
        patch("subprocess.run", return_value=mock_result),
        patch.dict(
            sys.modules,
            {
                "switcher.config": MagicMock(
                    load_config=MagicMock(return_value=_config(threshold=10))
                ),
                "switcher.state": state_mock,
                "switcher.utils": utils_mock,
                "switcher.hooks.gemini_after_agent": after_agent_mock,
            },
        ),
    ):
        main()

    result = json.loads(out_buf.getvalue())
    assert "systemMessage" in result
    assert "personal" in result["systemMessage"]


def test_main_cache_hit_quota_below_threshold_switch_fails_returns_empty(
    tmp_path: Path,
) -> None:
    """Switch subprocess fails (non-zero exit) → return {}."""
    config_dir = tmp_path / ".config" / "ai-account-switcher"
    profile_dir = config_dir / "profiles" / "gemini" / "work"
    profile_dir.mkdir(parents=True)

    cache_file = config_dir / "cache" / "quota_gemini.json"
    _save_quota_cache(cache_file, {"gemini-pro": 0.02}, ttl=300)

    mock_result = SimpleNamespace(returncode=1, stdout="", stderr="error")
    after_agent_mock = MagicMock()
    after_agent_mock._find_switcher.return_value = "/fake/switcher"

    state_mock = MagicMock()
    state_mock.get_active_profile.return_value = "work"

    utils_mock = MagicMock()
    utils_mock.get_config_dir.return_value = config_dir

    with (
        patch.object(sys, "stdin", io.TextIOWrapper(io.BytesIO(b"{}"))),
        patch.object(sys, "stdout", out_buf := io.StringIO()),
        patch("subprocess.run", return_value=mock_result),
        patch.dict(
            sys.modules,
            {
                "switcher.config": MagicMock(
                    load_config=MagicMock(return_value=_config(threshold=10))
                ),
                "switcher.state": state_mock,
                "switcher.utils": utils_mock,
                "switcher.hooks.gemini_after_agent": after_agent_mock,
            },
        ),
    ):
        main()

    result = json.loads(out_buf.getvalue())
    assert result == {}


# ---------------------------------------------------------------------------
# main() — cache miss: fetch fresh quota
# ---------------------------------------------------------------------------


def test_main_cache_miss_fetches_and_saves_quota(tmp_path: Path) -> None:
    """When cache is expired, fetches fresh quota and saves it."""
    config_dir = tmp_path / ".config" / "ai-account-switcher"
    profile_dir = config_dir / "profiles" / "gemini" / "work"
    profile_dir.mkdir(parents=True)

    # Write creds with access_token (no cache)
    _write_creds(profile_dir, {"access_token": "valid-token"})

    # Quota above threshold → no switch
    project_resp = MagicMock()
    project_resp.status_code = 200
    project_resp.json.return_value = {"cloudaicompanionProject": "proj"}

    quota_resp = MagicMock()
    quota_resp.status_code = 200
    quota_resp.json.return_value = {
        "userQuota": [{"modelName": "gemini-pro", "remainingFraction": 0.80}]
    }

    state_mock = MagicMock()
    state_mock.get_active_profile.return_value = "work"

    utils_mock = MagicMock()
    utils_mock.get_config_dir.return_value = config_dir

    with (
        patch.object(sys, "stdin", io.TextIOWrapper(io.BytesIO(b"{}"))),
        patch.object(sys, "stdout", out_buf := io.StringIO()),
        patch("requests.post", side_effect=[project_resp, quota_resp]),
        patch.dict(
            sys.modules,
            {
                "switcher.config": MagicMock(
                    load_config=MagicMock(return_value=_config(threshold=10))
                ),
                "switcher.state": state_mock,
                "switcher.utils": utils_mock,
            },
        ),
    ):
        main()

    result = json.loads(out_buf.getvalue())
    assert result == {}

    # Cache file should now exist
    cache_file = config_dir / "cache" / "quota_gemini.json"
    assert cache_file.exists()
    cached = json.loads(cache_file.read_text())
    assert cached["quotas"] == {"gemini-pro": 0.80}


def test_main_cache_miss_no_access_token_returns_empty(tmp_path: Path) -> None:
    """If we can't get an access token, return {}."""
    config_dir = tmp_path / ".config" / "ai-account-switcher"
    profile_dir = config_dir / "profiles" / "gemini" / "work"
    profile_dir.mkdir(parents=True)
    # No oauth_creds.json file written

    state_mock = MagicMock()
    state_mock.get_active_profile.return_value = "work"

    utils_mock = MagicMock()
    utils_mock.get_config_dir.return_value = config_dir

    with (
        patch.object(sys, "stdin", io.TextIOWrapper(io.BytesIO(b"{}"))),
        patch.object(sys, "stdout", out_buf := io.StringIO()),
        patch.dict(
            sys.modules,
            {
                "switcher.config": MagicMock(
                    load_config=MagicMock(return_value=_config())
                ),
                "switcher.state": state_mock,
                "switcher.utils": utils_mock,
            },
        ),
    ):
        main()

    assert json.loads(out_buf.getvalue()) == {}


def test_main_cache_miss_fetch_fails_returns_empty(tmp_path: Path) -> None:
    """If quota fetch fails (None), return {}."""
    config_dir = tmp_path / ".config" / "ai-account-switcher"
    profile_dir = config_dir / "profiles" / "gemini" / "work"
    profile_dir.mkdir(parents=True)
    _write_creds(profile_dir, {"access_token": "token"})

    # Both requests fail
    mock_resp = MagicMock()
    mock_resp.status_code = 500

    state_mock = MagicMock()
    state_mock.get_active_profile.return_value = "work"

    utils_mock = MagicMock()
    utils_mock.get_config_dir.return_value = config_dir

    with (
        patch.object(sys, "stdin", io.TextIOWrapper(io.BytesIO(b"{}"))),
        patch.object(sys, "stdout", out_buf := io.StringIO()),
        patch("requests.post", return_value=mock_resp),
        patch.dict(
            sys.modules,
            {
                "switcher.config": MagicMock(
                    load_config=MagicMock(return_value=_config())
                ),
                "switcher.state": state_mock,
                "switcher.utils": utils_mock,
            },
        ),
    ):
        main()

    assert json.loads(out_buf.getvalue()) == {}


# ---------------------------------------------------------------------------
# main() — exception safety
# ---------------------------------------------------------------------------


def test_main_invalid_stdin_returns_empty() -> None:
    """Corrupt stdin JSON must not crash main() — output {} and exit 0."""
    with (
        patch.object(sys, "stdin", io.TextIOWrapper(io.BytesIO(b"NOT JSON"))),
        patch.object(sys, "stdout", out_buf := io.StringIO()),
    ):
        main()

    assert json.loads(out_buf.getvalue()) == {}
