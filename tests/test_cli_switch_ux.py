"""UX tests for Gemini switch flow around OAuth prompts."""

from __future__ import annotations

import argparse
import json
from typing import TYPE_CHECKING

from switcher import cli
from switcher.profiles.base import Profile

if TYPE_CHECKING:
    from pathlib import Path

    from pytest import MonkeyPatch


class _DummyManager:
    def __init__(self, profile: Profile) -> None:
        self._profile = profile
        self.switched_to: str | None = None

    def get_profile(self, _identifier: str) -> Profile:
        return self._profile

    def switch_to(self, identifier: str) -> str:
        self.switched_to = identifier
        return identifier


def test_switch_uses_profile_keyring_backup_without_reprompt(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    profile_dir = tmp_path / "personal"
    profile_dir.mkdir(parents=True)
    (profile_dir / "keyring_creds.json").write_text(
        json.dumps(
            {
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
        ),
        encoding="utf-8",
    )
    profile = Profile(label="personal", auth_type="oauth", path=profile_dir)
    manager = _DummyManager(profile)

    monkeypatch.setattr(cli, "_get_manager", lambda _name: manager)
    monkeypatch.setattr(
        cli,
        "confirm",
        lambda _prompt: (_ for _ in ()).throw(
            AssertionError("switch should not prompt for OAuth")
        ),
    )
    monkeypatch.setattr(
        cli,
        "_run_gemini_oauth_enrollment",
        lambda _profile: (_ for _ in ()).throw(
            AssertionError("switch should not re-run enrollment")
        ),
    )

    cli.cmd_switch(argparse.Namespace(target="personal"), cli_name="gemini")

    assert manager.switched_to == "personal"
    creds_payload = json.loads(
        (profile_dir / "oauth_creds.json").read_text(encoding="utf-8")
    )
    assert creds_payload["refreshToken"] == "refresh-token"
