"""Tests for Gemini OAuth recovery paths in CLI enrollment flow."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from switcher import cli
from switcher.auth import keyring_backend
from switcher.profiles.base import Profile

if TYPE_CHECKING:
    from pathlib import Path

    from pytest import MonkeyPatch


def test_recover_profile_oauth_from_keyring_writes_profile_files(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    profile_dir = tmp_path / "personal"
    profile_dir.mkdir(parents=True)
    profile = Profile(label="personal", auth_type="oauth", path=profile_dir)

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
        keyring_backend,
        "keyring_read",
        lambda _service, _key: json.dumps(keyring_payload),
    )

    recovered = cli._recover_profile_oauth_from_keyring(profile)
    assert recovered

    creds = json.loads((profile_dir / "oauth_creds.json").read_text(encoding="utf-8"))
    assert creds["accessToken"] == "access-token"
    assert creds["refreshToken"] == "refresh-token"
    assert (profile_dir / "keyring_creds.json").exists()
