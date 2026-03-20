"""Tests for auth discovery helpers."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

from switcher.discovery import (
    adopt_discovered_auth,
    default_adopt_label,
    discover_codex_auth,
    discover_existing_auth,
    discover_gemini_auth,
)

if TYPE_CHECKING:
    from pathlib import Path


def test_discover_gemini_auth_missing_file(tmp_path: Path) -> None:
    from unittest.mock import patch

    with patch("switcher.discovery.keyring_read", return_value=None):
        result = discover_gemini_auth(tmp_path / "oauth_creds.json")
    assert result.found is False
    assert result.valid is False
    assert "not found" in result.reason.lower()


def test_discover_gemini_auth_valid_nested_token(tmp_path: Path) -> None:
    creds = {"token": {"refreshToken": "rt", "accessToken": "at"}}
    path = tmp_path / "oauth_creds.json"
    path.write_text(json.dumps(creds), encoding="utf-8")

    result = discover_gemini_auth(path)
    assert result.found is True
    assert result.valid is True
    assert result.detected_auth_type == "oauth"


def test_discover_gemini_auth_invalid_payload(tmp_path: Path) -> None:
    path = tmp_path / "oauth_creds.json"
    path.write_text(json.dumps({"token": {}}), encoding="utf-8")

    result = discover_gemini_auth(path)
    assert result.found is True
    assert result.valid is False
    assert "missing oauth token fields" in result.reason.lower()
    assert result.detected_auth_type is None


def test_discover_codex_auth_valid_flat_api_key(tmp_path: Path) -> None:
    path = tmp_path / "auth.json"
    path.write_text(json.dumps({"api_key": "sk-test", "account_id": "acct"}))

    result = discover_codex_auth(path)
    assert result.found is True
    assert result.valid is True
    assert result.detected_auth_type == "apikey"


def test_discover_codex_auth_invalid(tmp_path: Path) -> None:
    path = tmp_path / "auth.json"
    path.write_text(json.dumps({"foo": "bar"}), encoding="utf-8")

    result = discover_codex_auth(path)
    assert result.found is True
    assert result.valid is False
    assert "invalid" in result.reason.lower()
    assert result.detected_auth_type is None


def test_discover_codex_auth_valid_chatgpt(tmp_path: Path) -> None:
    path = tmp_path / "auth.json"
    path.write_text(json.dumps({"access_token": "at-123", "account_id": "acct"}))

    result = discover_codex_auth(path)
    assert result.found is True
    assert result.valid is True
    assert result.detected_auth_type == "chatgpt"


def test_discover_gemini_auth_keyring_only_signal(tmp_path: Path) -> None:
    from unittest.mock import patch

    with patch("switcher.discovery.keyring_read", return_value="{}"):
        result = discover_gemini_auth(tmp_path / "oauth_creds.json")

    assert result.found is True
    assert result.valid is False
    assert "keyring-only mode" in result.reason.lower()
    assert result.detected_auth_type == "oauth"


def test_discover_gemini_auth_keyring_probe_failure_is_non_fatal(
    tmp_path: Path,
) -> None:
    from unittest.mock import patch

    with patch("switcher.discovery.keyring_read", side_effect=RuntimeError("boom")):
        result = discover_gemini_auth(tmp_path / "oauth_creds.json")

    assert result.found is False
    assert result.valid is False
    assert "not found" in result.reason.lower()


def test_discover_codex_auth_keyring_mode_signal(tmp_path: Path) -> None:
    from unittest.mock import patch

    with patch("switcher.discovery.detect_keyring_mode", return_value="keyring"):
        result = discover_codex_auth(tmp_path / "auth.json")

    assert result.found is True
    assert result.valid is False
    assert "keyring-backed" in result.reason.lower()


def test_discover_codex_auth_missing_file_in_file_mode(tmp_path: Path) -> None:
    from unittest.mock import patch

    with patch("switcher.discovery.detect_keyring_mode", return_value="file"):
        result = discover_codex_auth(tmp_path / "auth.json")

    assert result.found is False
    assert result.valid is False
    assert "not found" in result.reason.lower()


def test_discover_existing_auth_uses_default_locations(tmp_path: Path) -> None:
    gemini_dir = tmp_path / ".gemini"
    codex_dir = tmp_path / ".codex"
    gemini_dir.mkdir()
    codex_dir.mkdir()

    (gemini_dir / "oauth_creds.json").write_text(
        json.dumps({"refreshToken": "rt"}), encoding="utf-8"
    )
    (codex_dir / "auth.json").write_text(
        json.dumps({"OPENAI_API_KEY": "sk-test"}), encoding="utf-8"
    )

    from unittest.mock import patch

    with (
        patch("switcher.discovery.get_gemini_dir", return_value=gemini_dir),
        patch("switcher.discovery.get_codex_dir", return_value=codex_dir),
    ):
        results = discover_existing_auth()

    assert results["gemini"].valid is True
    assert results["codex"].valid is True


def test_default_adopt_label_is_deterministic_and_unique() -> None:
    label = default_adopt_label("gemini", {"personal-gemini", "work"})
    assert label == "personal-gemini-2"

    label2 = default_adopt_label(
        "gemini", {"personal-gemini", "personal-gemini-2"}
    )
    assert label2 == "personal-gemini-3"


def test_adopt_discovered_auth_returns_none_when_invalid(tmp_path: Path) -> None:
    result = discover_gemini_auth(tmp_path / "missing.json")
    mgr = MagicMock()
    adopted = adopt_discovered_auth(result, mgr)
    assert adopted is None
    mgr.import_credentials.assert_not_called()


def test_adopt_discovered_auth_imports_with_default_label(tmp_path: Path) -> None:
    creds = tmp_path / "oauth_creds.json"
    creds.write_text(json.dumps({"refreshToken": "rt"}), encoding="utf-8")
    result = discover_gemini_auth(creds)

    existing_profile = MagicMock()
    existing_profile.label = "personal-gemini"
    manager = MagicMock()
    manager.list_profiles.return_value = [existing_profile]
    imported = MagicMock()
    manager.import_credentials.return_value = imported

    adopted = adopt_discovered_auth(result, manager)
    assert adopted is imported
    manager.import_credentials.assert_called_once_with(
        creds, "personal-gemini-2"
    )


def test_adopt_discovered_auth_respects_explicit_label(tmp_path: Path) -> None:
    auth = tmp_path / "auth.json"
    auth.write_text(json.dumps({"OPENAI_API_KEY": "sk-test"}), encoding="utf-8")
    result = discover_codex_auth(auth)

    manager = MagicMock()
    manager.list_profiles.return_value = []
    imported = MagicMock()
    manager.import_credentials.return_value = imported

    adopted = adopt_discovered_auth(result, manager, label="my-codex")
    assert adopted is imported
    manager.import_credentials.assert_called_once_with(auth, "my-codex")
