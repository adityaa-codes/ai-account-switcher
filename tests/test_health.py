"""Tests for profile health checking."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import requests

from switcher.health import (
    check_all_profiles,
    check_codex_apikey,
    check_codex_chatgpt,
    check_gemini_apikey,
    check_gemini_oauth,
    check_profile,
    interpret_http_status,
)
from switcher.profiles.base import Profile

if TYPE_CHECKING:
    from pathlib import Path


# ── interpret_http_status ───────────────────────────────────────────────────


def test_interpret_http_status_200_is_valid() -> None:
    assert interpret_http_status(200) == "valid"


def test_interpret_http_status_401_is_revoked() -> None:
    assert interpret_http_status(401) == "revoked"


def test_interpret_http_status_403_is_revoked() -> None:
    assert interpret_http_status(403) == "revoked"


def test_interpret_http_status_429_is_valid() -> None:
    # Rate-limited but token is valid
    assert interpret_http_status(429) == "valid"


def test_interpret_http_status_500_is_unknown() -> None:
    assert interpret_http_status(500) == "unknown"


# ── check_gemini_oauth ──────────────────────────────────────────────────────


def test_check_gemini_oauth_missing_creds(tmp_path: Path) -> None:
    status, detail = check_gemini_oauth(tmp_path)
    assert status == "expired"
    assert "Missing" in detail


def test_check_gemini_oauth_no_refresh_token(tmp_path: Path) -> None:
    creds = tmp_path / "oauth_creds.json"
    creds.write_text(json.dumps({"accessToken": "at"}), encoding="utf-8")
    status, detail = check_gemini_oauth(tmp_path)
    assert status == "expired"
    assert "refresh token" in detail.lower()


def test_check_gemini_oauth_corrupt_json(tmp_path: Path) -> None:
    (tmp_path / "oauth_creds.json").write_text("{bad json", encoding="utf-8")
    status, _ = check_gemini_oauth(tmp_path)
    assert status == "expired"


def test_check_gemini_oauth_valid_on_200(tmp_path: Path) -> None:
    (tmp_path / "oauth_creds.json").write_text(
        json.dumps({"refreshToken": "rt"}), encoding="utf-8"
    )
    mock_resp = MagicMock()
    mock_resp.status_code = 200

    with patch("switcher.health.requests.post", return_value=mock_resp):
        status, _ = check_gemini_oauth(tmp_path)

    assert status == "valid"


def test_check_gemini_oauth_revoked_on_invalid_grant(tmp_path: Path) -> None:
    (tmp_path / "oauth_creds.json").write_text(
        json.dumps({"refreshToken": "rt"}), encoding="utf-8"
    )
    mock_resp = MagicMock()
    mock_resp.status_code = 400
    mock_resp.json.return_value = {"error": "invalid_grant"}

    with patch("switcher.health.requests.post", return_value=mock_resp):
        status, _ = check_gemini_oauth(tmp_path)

    assert status == "revoked"


def test_check_gemini_oauth_retries_without_secret_on_400_invalid_client(
    tmp_path: Path,
) -> None:
    (tmp_path / "oauth_creds.json").write_text(
        json.dumps({"refreshToken": "rt"}), encoding="utf-8"
    )

    first = MagicMock()
    first.status_code = 400
    first.json.return_value = {"error": "invalid_client"}

    second = MagicMock()
    second.status_code = 200

    with patch(
        "switcher.health.requests.post", side_effect=[first, second]
    ) as mock_post:
        status, detail = check_gemini_oauth(tmp_path)

    assert status == "valid"
    assert "successfully" in detail.lower()
    assert mock_post.call_count == 2


def test_check_gemini_oauth_network_error(tmp_path: Path) -> None:
    (tmp_path / "oauth_creds.json").write_text(
        json.dumps({"refreshToken": "rt"}), encoding="utf-8"
    )
    with patch(
        "switcher.health.requests.post",
        side_effect=requests.RequestException("timeout"),
    ):
        status, detail = check_gemini_oauth(tmp_path)

    assert status == "unknown"
    assert "Network error" in detail


# ── check_gemini_apikey ─────────────────────────────────────────────────────


def test_check_gemini_apikey_missing_file(tmp_path: Path) -> None:
    profile_dir = tmp_path / "profile"
    profile_dir.mkdir()
    status, detail = check_profile("gemini", _make_profile(profile_dir, "apikey"))
    assert status == "expired"
    assert "Missing" in detail


def test_check_gemini_apikey_valid(tmp_path: Path) -> None:
    mock_resp = MagicMock()
    mock_resp.status_code = 200

    with patch("switcher.health.requests.get", return_value=mock_resp):
        status, _ = check_gemini_apikey("AIzaFakeKey")

    assert status == "valid"


def test_check_gemini_apikey_revoked(tmp_path: Path) -> None:
    mock_resp = MagicMock()
    mock_resp.status_code = 403

    with patch("switcher.health.requests.get", return_value=mock_resp):
        status, _ = check_gemini_apikey("AIzaFakeKey")

    assert status == "revoked"


# ── check_codex_apikey ──────────────────────────────────────────────────────


def test_check_codex_apikey_valid() -> None:
    mock_resp = MagicMock()
    mock_resp.status_code = 200

    with patch("switcher.health.requests.get", return_value=mock_resp):
        status, detail = check_codex_apikey("sk-test-key")

    assert status == "valid"
    assert "valid" in detail.lower()


def test_check_codex_apikey_revoked() -> None:
    mock_resp = MagicMock()
    mock_resp.status_code = 401

    with patch("switcher.health.requests.get", return_value=mock_resp):
        status, _ = check_codex_apikey("sk-test-key")

    assert status == "revoked"


def test_check_codex_apikey_network_error() -> None:
    with patch(
        "switcher.health.requests.get",
        side_effect=requests.RequestException("timeout"),
    ):
        status, detail = check_codex_apikey("sk-test-key")

    assert status == "unknown"
    assert "Network error" in detail


# ── check_codex_chatgpt ─────────────────────────────────────────────────────


def test_check_codex_chatgpt_missing_auth(tmp_path: Path) -> None:
    status, detail = check_codex_chatgpt(tmp_path)
    assert status == "expired"
    assert "Missing" in detail


def test_check_codex_chatgpt_no_tokens(tmp_path: Path) -> None:
    (tmp_path / "auth.json").write_text(
        json.dumps({"OPENAI_API_KEY": None, "tokens": None}), encoding="utf-8"
    )
    status, _ = check_codex_chatgpt(tmp_path)
    assert status == "expired"


def test_check_codex_chatgpt_valid(tmp_path: Path) -> None:
    (tmp_path / "auth.json").write_text(
        json.dumps({"tokens": {"refresh_token": "rt"}}), encoding="utf-8"
    )
    mock_resp = MagicMock()
    mock_resp.status_code = 200

    with patch("switcher.health.requests.post", return_value=mock_resp):
        status, _ = check_codex_chatgpt(tmp_path)

    assert status == "valid"


def test_check_codex_chatgpt_flat_access_token_returns_unknown(tmp_path: Path) -> None:
    (tmp_path / "auth.json").write_text(
        json.dumps({"access_token": "at", "account_id": "acct_123"}),
        encoding="utf-8",
    )
    status, detail = check_codex_chatgpt(tmp_path)
    assert status == "unknown"
    assert "access token" in detail.lower()


def test_check_codex_chatgpt_400_with_access_token_returns_unknown(
    tmp_path: Path,
) -> None:
    (tmp_path / "auth.json").write_text(
        json.dumps(
            {
                "tokens": {"refresh_token": "rt", "access_token": "at"},
                "account_id": "acct_123",
            }
        ),
        encoding="utf-8",
    )
    mock_resp = MagicMock()
    mock_resp.status_code = 400
    mock_resp.json.return_value = {"error": "invalid_request"}

    with patch("switcher.health.requests.post", return_value=mock_resp):
        status, detail = check_codex_chatgpt(tmp_path)

    assert status == "unknown"
    assert "http 400" in detail.lower()


# ── check_all_profiles ──────────────────────────────────────────────────────


def test_check_all_profiles_updates_meta(tmp_path: Path) -> None:
    profile_dir = tmp_path / "profile"
    profile_dir.mkdir()
    (profile_dir / "meta.json").write_text(
        json.dumps(
            {
                "label": "test",
                "auth_type": "apikey",
                "added_at": "2024-01-01T00:00:00+00:00",
                "last_used": None,
                "last_health_check": None,
                "health_status": "unknown",
                "health_detail": None,
                "notes": "",
            }
        ),
        encoding="utf-8",
    )
    profile = _make_profile(profile_dir, "apikey")

    mock_resp = MagicMock()
    mock_resp.status_code = 200

    with patch("switcher.health.requests.get", return_value=mock_resp):
        # needs api_key.txt to exist
        (profile_dir / "api_key.txt").write_text("AIzaFakeKey", encoding="utf-8")
        results = check_all_profiles("gemini", [profile])

    assert len(results) == 1
    _, status, _, _qi = results[0]
    assert status == "valid"

    meta = json.loads((profile_dir / "meta.json").read_text(encoding="utf-8"))
    assert meta["health_status"] == "valid"
    assert meta["last_health_check"] is not None


def test_check_profile_unknown_auth_type(tmp_path: Path) -> None:
    profile_dir = tmp_path / "profile"
    profile_dir.mkdir()
    profile = _make_profile(profile_dir, "unknown_type")
    status, _ = check_profile("gemini", profile)
    assert status == "unknown"


# ── helpers ─────────────────────────────────────────────────────────────────


def _make_profile(path: Path, auth_type: str) -> Profile:
    return Profile(
        label=path.name,
        auth_type=auth_type,
        path=path,
        meta={"auth_type": auth_type},
    )


# ---------------------------------------------------------------------------
# check_profile — codex paths
# ---------------------------------------------------------------------------


def _make_health_profile(tmp_path: Path, auth_type: str, **files: str) -> MagicMock:
    profile_dir = tmp_path / "profile"
    profile_dir.mkdir(parents=True, exist_ok=True)
    for name, content in files.items():
        (profile_dir / name).write_text(content)
    p = MagicMock()
    p.auth_type = auth_type
    p.meta = {"auth_type": auth_type}
    p.path = profile_dir
    return p


def test_check_profile_codex_apikey_valid(tmp_path: Path) -> None:
    import json

    from switcher.health import check_profile

    auth = json.dumps({"OPENAI_API_KEY": "sk-test-key", "tokens": None})
    profile = _make_health_profile(tmp_path, "apikey", **{"auth.json": auth})

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    with patch("switcher.health.requests.get", return_value=mock_resp):
        status, _detail = check_profile("codex", profile)
    assert status == "valid"


def test_check_profile_codex_apikey_missing_auth(tmp_path: Path) -> None:
    from switcher.health import check_profile

    profile = _make_health_profile(tmp_path, "apikey")  # no auth.json
    status, detail = check_profile("codex", profile)
    assert status == "expired"
    assert "Missing" in detail


def test_check_profile_codex_apikey_no_key_in_auth(tmp_path: Path) -> None:
    import json

    from switcher.health import check_profile

    auth = json.dumps({"OPENAI_API_KEY": "", "tokens": None})
    profile = _make_health_profile(tmp_path, "apikey", **{"auth.json": auth})
    status, _detail = check_profile("codex", profile)
    assert status == "expired"


def test_check_profile_codex_apikey_corrupt_auth(tmp_path: Path) -> None:
    from switcher.health import check_profile

    profile = _make_health_profile(tmp_path, "apikey", **{"auth.json": "{bad json"})
    status, _detail = check_profile("codex", profile)
    assert status == "expired"


def test_check_profile_codex_chatgpt(tmp_path: Path) -> None:
    import json

    from switcher.health import check_profile

    auth = json.dumps({"OPENAI_API_KEY": None, "tokens": {"refresh_token": "rt-abc"}})
    profile = _make_health_profile(tmp_path, "chatgpt", **{"auth.json": auth})

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    with patch("switcher.health.requests.post", return_value=mock_resp):
        status, _detail = check_profile("codex", profile)
    assert status == "valid"


def test_check_profile_codex_apikey_flat_api_key_format(tmp_path: Path) -> None:
    import json

    from switcher.health import check_profile

    auth = json.dumps({"api_key": "sk-test-key", "account_id": "acct_123"})
    profile = _make_health_profile(tmp_path, "apikey", **{"auth.json": auth})

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    with patch("switcher.health.requests.get", return_value=mock_resp):
        status, _detail = check_profile("codex", profile)
    assert status == "valid"


def test_check_profile_unknown_auth_type_codex(tmp_path: Path) -> None:
    from switcher.health import check_profile

    profile = _make_health_profile(tmp_path, "foobar")
    status, _detail = check_profile("codex", profile)
    assert status == "unknown"
    assert "foobar" in _detail


def test_check_profile_unknown_cli(tmp_path: Path) -> None:
    from switcher.health import check_profile

    profile = _make_health_profile(tmp_path, "apikey")
    status, _detail = check_profile("unknown_cli", profile)
    assert status == "unknown"


# ---------------------------------------------------------------------------
# _oauth_error_detail — error branches
# ---------------------------------------------------------------------------


def test_oauth_error_detail_invalid_json() -> None:
    from switcher.health import _oauth_error_detail

    mock_resp = MagicMock()
    mock_resp.json.side_effect = ValueError("not json")
    error, desc = _oauth_error_detail(mock_resp)
    assert error == ""
    assert desc == ""


def test_oauth_error_detail_non_dict_payload() -> None:
    from switcher.health import _oauth_error_detail

    mock_resp = MagicMock()
    mock_resp.json.return_value = ["not", "a", "dict"]
    error, _desc = _oauth_error_detail(mock_resp)
    assert error == ""


# ---------------------------------------------------------------------------
# check_codex_apikey — network error (additional coverage)
# ---------------------------------------------------------------------------


def test_check_codex_apikey_network_error_2() -> None:
    import requests as req

    from switcher.health import check_codex_apikey

    with patch(
        "switcher.health.requests.get",
        side_effect=req.RequestException("timeout"),
    ):
        status, detail = check_codex_apikey("sk-test")
    assert status == "unknown"
    assert "Network error" in detail


# ---------------------------------------------------------------------------
# check_gemini_apikey — non-200 status
# ---------------------------------------------------------------------------


def test_check_gemini_apikey_unauthorized() -> None:
    from switcher.health import check_gemini_apikey

    mock_resp = MagicMock()
    mock_resp.status_code = 403
    with patch("switcher.health.requests.get", return_value=mock_resp):
        status, _detail = check_gemini_apikey("bad-key")
    assert status != "valid"


# ---------------------------------------------------------------------------
# _read_access_token
# ---------------------------------------------------------------------------


def test_read_access_token_flat_format(tmp_path: Path) -> None:
    from switcher.health import _read_access_token

    creds = tmp_path / "oauth_creds.json"
    creds.write_text('{"access_token": "flat-token"}')
    assert _read_access_token(tmp_path) == "flat-token"


def test_read_access_token_nested_format(tmp_path: Path) -> None:
    from switcher.health import _read_access_token

    creds = tmp_path / "oauth_creds.json"
    creds.write_text('{"token": {"accessToken": "nested-token"}}')
    assert _read_access_token(tmp_path) == "nested-token"


def test_read_access_token_missing_file(tmp_path: Path) -> None:
    from switcher.health import _read_access_token

    assert _read_access_token(tmp_path) is None


def test_read_access_token_corrupt_json(tmp_path: Path) -> None:
    from switcher.health import _read_access_token

    (tmp_path / "oauth_creds.json").write_text("{bad")
    assert _read_access_token(tmp_path) is None


# ---------------------------------------------------------------------------
# _refresh_access_token
# ---------------------------------------------------------------------------


def test_refresh_access_token_no_creds_file(tmp_path: Path) -> None:
    from switcher.health import _refresh_access_token

    # No oauth_creds.json — falls back to _read_access_token which returns None
    assert _refresh_access_token(tmp_path) is None


def test_refresh_access_token_no_refresh_token_falls_back(tmp_path: Path) -> None:
    from switcher.health import _refresh_access_token

    (tmp_path / "oauth_creds.json").write_text('{"access_token": "cached-at"}')
    assert _refresh_access_token(tmp_path) == "cached-at"


def test_refresh_access_token_success(tmp_path: Path) -> None:
    import json

    from switcher.health import _refresh_access_token

    creds = {"token": {"refreshToken": "rt-xyz", "accessToken": "old-at"}}
    (tmp_path / "oauth_creds.json").write_text(json.dumps(creds))

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"access_token": "fresh-at"}

    with patch("switcher.health.requests.post", return_value=mock_resp):
        token = _refresh_access_token(tmp_path)
    assert token == "fresh-at"


def test_refresh_access_token_fails_returns_cached(tmp_path: Path) -> None:
    import json

    from switcher.health import _refresh_access_token

    creds = {"token": {"refreshToken": "rt-xyz", "accessToken": "cached"}}
    (tmp_path / "oauth_creds.json").write_text(json.dumps(creds))

    mock_resp = MagicMock()
    mock_resp.status_code = 401

    with patch("switcher.health.requests.post", return_value=mock_resp):
        token = _refresh_access_token(tmp_path)
    assert token == "cached"


# ---------------------------------------------------------------------------
# _fetch_google_email
# ---------------------------------------------------------------------------


def test_fetch_google_email_success() -> None:
    from switcher.health import _fetch_google_email

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"email": "alice@example.com"}

    with patch("switcher.health.requests.get", return_value=mock_resp):
        assert _fetch_google_email("tok") == "alice@example.com"


def test_fetch_google_email_non_200() -> None:
    from switcher.health import _fetch_google_email

    mock_resp = MagicMock()
    mock_resp.status_code = 401
    with patch("switcher.health.requests.get", return_value=mock_resp):
        assert _fetch_google_email("bad") is None


def test_fetch_google_email_network_error() -> None:
    import requests as req

    from switcher.health import _fetch_google_email

    with patch(
        "switcher.health.requests.get",
        side_effect=req.RequestException("timeout"),
    ):
        assert _fetch_google_email("tok") is None


# ---------------------------------------------------------------------------
# fetch_quota_info
# ---------------------------------------------------------------------------


def test_fetch_quota_info_no_access_token(tmp_path: Path) -> None:
    from switcher.health import fetch_quota_info

    profile = _make_profile(tmp_path / "p", "oauth")
    qi = fetch_quota_info(profile)
    assert qi.error is not None
    assert "access token" in qi.error.lower()


def test_fetch_quota_info_load_assist_fails(tmp_path: Path) -> None:
    import json

    from switcher.health import fetch_quota_info

    profile_dir = tmp_path / "p"
    profile_dir.mkdir()
    (profile_dir / "oauth_creds.json").write_text(json.dumps({"access_token": "tok"}))
    profile = _make_profile(profile_dir, "oauth")

    fail_resp = MagicMock()
    fail_resp.status_code = 500

    with (
        patch("switcher.health.requests.post", return_value=fail_resp),
        patch("switcher.health.requests.get") as mock_get,
    ):
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {"email": "a@b.com"}
        qi = fetch_quota_info(profile)

    assert qi.error is not None
    assert "loadCodeAssist" in qi.error


def test_fetch_quota_info_success(tmp_path: Path) -> None:
    import json

    from switcher.health import QuotaEntry, fetch_quota_info

    profile_dir = tmp_path / "p"
    profile_dir.mkdir()
    (profile_dir / "oauth_creds.json").write_text(json.dumps({"access_token": "tok"}))
    profile = _make_profile(profile_dir, "oauth")

    load_resp = MagicMock()
    load_resp.status_code = 200
    load_resp.json.return_value = {"cloudaicompanionProject": "proj-123"}

    quota_resp = MagicMock()
    quota_resp.status_code = 200
    quota_resp.json.return_value = {
        "userQuota": [
            {
                "modelName": "gemini-2.5-pro",
                "remainingFraction": 0.73,
                "currentPeriodEnd": "2025-04-01T00:00:00Z",
            },
            {"modelName": "gemini-2.0-flash", "remainingFraction": 0.45},
        ]
    }

    with (
        patch("switcher.health.requests.post", side_effect=[load_resp, quota_resp]),
        patch("switcher.health.requests.get") as mock_get,
    ):
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {"email": "alice@example.com"}
        qi = fetch_quota_info(profile)

    assert qi.email == "alice@example.com"
    assert qi.error is None
    assert len(qi.quotas) == 2
    assert isinstance(qi.quotas[0], QuotaEntry)
    assert qi.quotas[0].model == "gemini-2.5-pro"
    assert abs(qi.quotas[0].remaining_pct - 73.0) < 0.01
    assert qi.quotas[0].reset_at == "2025-04-01T00:00:00Z"
    assert qi.quotas[1].reset_at is None


def test_fetch_quota_info_network_error(tmp_path: Path) -> None:
    import json

    import requests as req

    from switcher.health import fetch_quota_info

    profile_dir = tmp_path / "p"
    profile_dir.mkdir()
    (profile_dir / "oauth_creds.json").write_text(json.dumps({"access_token": "tok"}))
    profile = _make_profile(profile_dir, "oauth")

    with (
        patch(
            "switcher.health.requests.post",
            side_effect=req.RequestException("timeout"),
        ),
        patch("switcher.health.requests.get") as mock_get,
    ):
        mock_get.return_value.status_code = 401
        qi = fetch_quota_info(profile)

    assert qi.error is not None
    assert "Network error" in qi.error


# ---------------------------------------------------------------------------
# Phase 1 — loadCodeAssist mode (B-1) and strftime portability (I-2)
# ---------------------------------------------------------------------------


def test_fetch_quota_info_sends_health_check_mode(tmp_path: Path) -> None:
    """B-1: loadCodeAssist request must include mode=HEALTH_CHECK."""
    import json as _json

    from switcher.health import fetch_quota_info

    profile_dir = tmp_path / "p"
    profile_dir.mkdir()
    (profile_dir / "oauth_creds.json").write_text(_json.dumps({"access_token": "tok"}))
    profile = _make_profile(profile_dir, "oauth")

    load_resp = MagicMock()
    load_resp.status_code = 200
    load_resp.json.return_value = {"cloudaicompanionProject": "proj-123"}

    quota_resp = MagicMock()
    quota_resp.status_code = 200
    quota_resp.json.return_value = {"userQuota": []}

    captured_calls: list = []

    def capture_post(url: str, **kwargs: object) -> MagicMock:
        captured_calls.append((url, kwargs))
        if "loadCodeAssist" in url:
            return load_resp
        return quota_resp

    with (
        patch("switcher.health.requests.post", side_effect=capture_post),
        patch("switcher.health.requests.get") as mock_get,
    ):
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {"email": "a@b.com"}
        fetch_quota_info(profile)

    load_calls = [kw for url, kw in captured_calls if "loadCodeAssist" in url]
    assert load_calls, "loadCodeAssist must be called"
    body = load_calls[0].get("json", {})
    assert body.get("mode") == "HEALTH_CHECK", (
        "mode must be HEALTH_CHECK to avoid billing side-effects"
    )
    assert "metadata" in body, "metadata field must be present"


def test_format_reset_date_single_digit_day() -> None:
    """I-2: _format_reset_date must not use %-d (GNU-only).

    Single-digit day should not have a leading zero.
    """
    from switcher.cli import _format_reset_date

    result = _format_reset_date("2025-04-01T00:00:00Z")
    assert result == "Apr 1 2025", f"Expected 'Apr 1 2025', got '{result}'"


def test_format_reset_date_double_digit_day() -> None:
    """I-2: _format_reset_date sanity check for double-digit day."""
    from switcher.cli import _format_reset_date

    result = _format_reset_date("2025-04-15T00:00:00Z")
    assert result == "Apr 15 2025", f"Expected 'Apr 15 2025', got '{result}'"


def test_format_reset_date_invalid_input_returns_original() -> None:
    """I-2: _format_reset_date must return the original string on parse error."""
    from switcher.cli import _format_reset_date

    bad = "not-a-date"
    assert _format_reset_date(bad) == bad


# ── Phase 2: C-1, C-2, B-2, B-3 ───────────────────────────────────────────



def test_google_oauth_clients_returns_only_discovered() -> None:
    """C-1: when discovery succeeds, _google_oauth_clients returns only that client."""
    from switcher.health import _google_oauth_clients

    with patch(
        "switcher.health._discover_gemini_oauth_client",
        return_value=("id1", "sec1"),
    ):
        clients = _google_oauth_clients()

    assert clients == [("id1", "sec1")], "Should return exactly the discovered client"


def test_google_oauth_clients_falls_back_when_discovery_fails() -> None:
    """C-1: when discovery returns None, falls back to hardcoded list and warns."""
    from switcher.health import _KNOWN_GOOGLE_OAUTH_CLIENTS, _google_oauth_clients

    with (
        patch("switcher.health._discover_gemini_oauth_client", return_value=None),
        patch("switcher.health.logger") as mock_log,
    ):
        clients = _google_oauth_clients()

    assert clients == list(_KNOWN_GOOGLE_OAUTH_CLIENTS), "Should use hardcoded fallback"
    mock_log.warning.assert_called_once()


def test_discover_tries_alternative_paths(tmp_path: Path) -> None:
    """C-2: _discover_gemini_oauth_client succeeds with auth/oauth2.js layout."""
    from switcher.health import _discover_gemini_oauth_client

    # Fake gemini binary: tmp_path/dist/index.js  → package_root = tmp_path
    bin_path = tmp_path / "dist" / "index.js"
    bin_path.parent.mkdir(parents=True)
    bin_path.write_text("// stub\n")

    core = tmp_path / "node_modules" / "@google" / "gemini-cli-core"
    # Place credentials at second candidate path (auth/oauth2.js)
    alt = core / "dist" / "src" / "auth" / "oauth2.js"
    alt.parent.mkdir(parents=True)
    alt.write_text("OAUTH_CLIENT_ID = 'alt_id'\nOAUTH_CLIENT_SECRET = 'alt_sec'\n")

    with (
        patch("switcher.health.shutil.which", return_value=str(bin_path)),
        patch("switcher.state.get_cached_oauth_client", return_value=None),
        patch("switcher.state.cache_oauth_client"),
    ):
        result = _discover_gemini_oauth_client()

    assert result == ("alt_id", "alt_sec"), f"Expected alt credentials, got {result!r}"


def test_fetch_quota_info_populates_tier(tmp_path: Path) -> None:
    """B-2: tier field populated from currentTier.tierName in response."""
    import json

    from switcher.health import fetch_quota_info

    profile_dir = tmp_path / "p"
    profile_dir.mkdir()
    (profile_dir / "oauth_creds.json").write_text(json.dumps({"access_token": "tok"}))
    profile = _make_profile(profile_dir, "oauth")

    load_resp = MagicMock()
    load_resp.status_code = 200
    load_resp.json.return_value = {
        "cloudaicompanionProject": "proj-x",
        "currentTier": {"tierName": "PREMIUM", "name": "premium"},
    }

    quota_resp = MagicMock()
    quota_resp.status_code = 200
    quota_resp.json.return_value = {"userQuota": []}

    def side_post(url: str, **kw: object) -> MagicMock:
        return load_resp if "loadCodeAssist" in url else quota_resp

    with (
        patch("switcher.health.requests.post", side_effect=side_post),
        patch("switcher.health.requests.get") as mg,
        patch("switcher.health._google_oauth_clients", return_value=[("id", "sec")]),
    ):
        mg.return_value.status_code = 200
        mg.return_value.json.return_value = {"email": "x@y.com"}
        info = fetch_quota_info(profile)

    assert info.tier == "PREMIUM", f"Expected tier='PREMIUM', got {info.tier!r}"


def test_fetch_quota_info_epoch_reset_normalised(tmp_path: Path) -> None:
    """B-3: Unix epoch integer reset_at is normalised to ISO 8601 string."""
    import json

    from switcher.health import fetch_quota_info

    epoch = 1_750_000_000  # a future Unix timestamp

    profile_dir = tmp_path / "p"
    profile_dir.mkdir()
    (profile_dir / "oauth_creds.json").write_text(json.dumps({"access_token": "tok"}))
    profile = _make_profile(profile_dir, "oauth")

    load_resp = MagicMock()
    load_resp.status_code = 200
    load_resp.json.return_value = {"cloudaicompanionProject": "proj-y"}

    quota_resp = MagicMock()
    quota_resp.status_code = 200
    quota_resp.json.return_value = {
        "userQuota": [
            {
                "modelName": "gemini-2.0-flash",
                "remainingFraction": 0.5,
                "resetAt": epoch,
            }
        ]
    }

    def side_post(url: str, **kw: object) -> MagicMock:
        return load_resp if "loadCodeAssist" in url else quota_resp

    with (
        patch("switcher.health.requests.post", side_effect=side_post),
        patch("switcher.health.requests.get") as mg,
        patch("switcher.health._google_oauth_clients", return_value=[("id", "sec")]),
    ):
        mg.return_value.status_code = 200
        mg.return_value.json.return_value = {"email": "x@y.com"}
        info = fetch_quota_info(profile)

    assert info.quotas, "Expected at least one quota entry"
    reset = info.quotas[0].reset_at
    assert reset is not None, "reset_at should not be None"
    is_iso = "T" in reset and (
        "+" in reset or "Z" in reset or reset.endswith("+00:00")
    )
    assert is_iso, f"reset_at should be ISO 8601, got {reset!r}"
