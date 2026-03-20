"""Tests for auth discovery helpers."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from switcher.discovery import (
    discover_codex_auth,
    discover_existing_auth,
    discover_gemini_auth,
)

if TYPE_CHECKING:
    from pathlib import Path


def test_discover_gemini_auth_missing_file(tmp_path: Path) -> None:
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


def test_discover_gemini_auth_invalid_payload(tmp_path: Path) -> None:
    path = tmp_path / "oauth_creds.json"
    path.write_text(json.dumps({"token": {}}), encoding="utf-8")

    result = discover_gemini_auth(path)
    assert result.found is True
    assert result.valid is False
    assert "missing oauth token fields" in result.reason.lower()


def test_discover_codex_auth_valid_flat_api_key(tmp_path: Path) -> None:
    path = tmp_path / "auth.json"
    path.write_text(json.dumps({"api_key": "sk-test", "account_id": "acct"}))

    result = discover_codex_auth(path)
    assert result.found is True
    assert result.valid is True


def test_discover_codex_auth_invalid(tmp_path: Path) -> None:
    path = tmp_path / "auth.json"
    path.write_text(json.dumps({"foo": "bar"}), encoding="utf-8")

    result = discover_codex_auth(path)
    assert result.found is True
    assert result.valid is False
    assert "invalid" in result.reason.lower()


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
