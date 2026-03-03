"""Tests for Gemini auth credential activation and backup behavior."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from switcher.auth import gemini_auth
from switcher.auth.gemini_auth import activate_oauth_profile, backup_current_credentials

if TYPE_CHECKING:
    from pathlib import Path

    from pytest import MonkeyPatch


def _set_test_home(monkeypatch: MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / ".config"))


def test_backup_current_credentials_backs_up_google_accounts(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    _set_test_home(monkeypatch, tmp_path)
    gemini_dir = tmp_path / ".gemini"
    gemini_dir.mkdir(parents=True)

    oauth_payload = '{"refreshToken":"token"}\n'
    accounts_payload = '{"active":"new@example.com","old":[]}\n'
    (gemini_dir / "oauth_creds.json").write_text(oauth_payload, encoding="utf-8")
    (gemini_dir / "google_accounts.json").write_text(accounts_payload, encoding="utf-8")

    backup_current_credentials("work")

    profile_dir = tmp_path / ".config" / "cli-switcher" / "profiles" / "gemini" / "work"
    assert (profile_dir / "oauth_creds.json").read_text(
        encoding="utf-8"
    ) == oauth_payload
    assert (profile_dir / "google_accounts.json").read_text(
        encoding="utf-8"
    ) == accounts_payload


def test_activate_oauth_profile_symlinks_google_accounts_and_clears_cache(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    _set_test_home(monkeypatch, tmp_path)

    profile_dir = tmp_path / "profile"
    profile_dir.mkdir(parents=True)
    creds_file = profile_dir / "oauth_creds.json"
    accounts_file = profile_dir / "google_accounts.json"
    creds_file.write_text('{"refreshToken":"token"}\n', encoding="utf-8")
    accounts_file.write_text(
        '{"active":"work@example.com","old":[]}\n', encoding="utf-8"
    )

    gemini_dir = tmp_path / ".gemini"
    gemini_dir.mkdir(parents=True)
    (gemini_dir / "mcp-oauth-tokens.json").write_text("stale", encoding="utf-8")

    activate_oauth_profile(profile_dir, storage_mode="file")

    oauth_target = gemini_dir / "oauth_creds.json"
    accounts_target = gemini_dir / "google_accounts.json"
    assert oauth_target.is_symlink()
    assert oauth_target.resolve() == creds_file.resolve()
    assert accounts_target.is_symlink()
    assert accounts_target.resolve() == accounts_file.resolve()
    assert not (gemini_dir / "mcp-oauth-tokens.json").exists()


def test_activate_oauth_profile_removes_stale_google_accounts_when_profile_missing(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    _set_test_home(monkeypatch, tmp_path)

    profile_dir = tmp_path / "profile"
    profile_dir.mkdir(parents=True)
    (profile_dir / "oauth_creds.json").write_text(
        '{"refreshToken":"token"}\n', encoding="utf-8"
    )

    gemini_dir = tmp_path / ".gemini"
    gemini_dir.mkdir(parents=True)
    (gemini_dir / "google_accounts.json").write_text(
        '{"active":"old@example.com","old":[]}\n', encoding="utf-8"
    )

    activate_oauth_profile(profile_dir, storage_mode="file")

    assert not (gemini_dir / "google_accounts.json").exists()


def test_backup_current_credentials_recovers_oauth_from_keyring_when_file_empty(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    _set_test_home(monkeypatch, tmp_path)
    gemini_dir = tmp_path / ".gemini"
    gemini_dir.mkdir(parents=True)
    (gemini_dir / "oauth_creds.json").write_text("{}\n", encoding="utf-8")

    keyring_payload = {
        "serverName": "main-account",
        "token": {
            "accessToken": "access-token",
            "refreshToken": "refresh-token",
            "tokenType": "Bearer",
            "scope": "scope",
            "expiresAt": 123,
        },
        "updatedAt": 999,
    }
    monkeypatch.setattr(
        gemini_auth, "keyring_read", lambda _service, _key: json.dumps(keyring_payload)
    )

    backup_current_credentials("work")

    profile_dir = tmp_path / ".config" / "cli-switcher" / "profiles" / "gemini" / "work"
    creds = json.loads((profile_dir / "oauth_creds.json").read_text(encoding="utf-8"))
    assert creds["accessToken"] == "access-token"
    assert creds["refreshToken"] == "refresh-token"
    assert (profile_dir / "keyring_creds.json").exists()


def test_activate_oauth_profile_recovers_from_profile_keyring_backup(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    _set_test_home(monkeypatch, tmp_path)
    profile_dir = tmp_path / "profile"
    profile_dir.mkdir(parents=True)
    keyring_payload = {
        "serverName": "main-account",
        "token": {
            "accessToken": "access-token",
            "refreshToken": "refresh-token",
            "tokenType": "Bearer",
            "scope": "scope",
            "expiresAt": 123,
        },
        "updatedAt": 999,
    }
    (profile_dir / "keyring_creds.json").write_text(
        json.dumps(keyring_payload), encoding="utf-8"
    )

    activate_oauth_profile(profile_dir, storage_mode="file")

    creds = json.loads((profile_dir / "oauth_creds.json").read_text(encoding="utf-8"))
    assert creds["accessToken"] == "access-token"
    assert creds["refreshToken"] == "refresh-token"
