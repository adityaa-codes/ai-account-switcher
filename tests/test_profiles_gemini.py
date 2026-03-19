"""Tests for GeminiProfileManager."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

from switcher.errors import AuthError, ProfileNotFoundError
from switcher.profiles.gemini import GeminiProfileManager

if TYPE_CHECKING:
    from pathlib import Path


def test_list_profiles_empty(tmp_config_dir: Path) -> None:
    mgr = GeminiProfileManager()
    assert mgr.list_profiles() == []


def test_add_profile_creates_directory_and_meta(tmp_config_dir: Path) -> None:
    mgr = GeminiProfileManager()
    profile = mgr.add_profile("work@example.com", "oauth")

    assert profile.label == "work@example.com"
    assert profile.auth_type == "oauth"
    assert profile.path.is_dir()
    meta = json.loads((profile.path / "meta.json").read_text(encoding="utf-8"))
    assert meta["auth_type"] == "oauth"
    assert meta["label"] == "work@example.com"


def test_add_profile_apikey_creates_directory(tmp_config_dir: Path) -> None:
    mgr = GeminiProfileManager()
    profile = mgr.add_profile("my-api-key", "apikey")
    assert profile.auth_type == "apikey"
    assert (profile.path / "meta.json").exists()


def test_add_profile_duplicate_raises(tmp_config_dir: Path) -> None:
    mgr = GeminiProfileManager()
    mgr.add_profile("work", "oauth")
    with pytest.raises(AuthError, match="already exists"):
        mgr.add_profile("work", "oauth")


def test_list_profiles_returns_all(tmp_config_dir: Path) -> None:
    mgr = GeminiProfileManager()
    mgr.add_profile("personal", "oauth")
    mgr.add_profile("work", "apikey")
    profiles = mgr.list_profiles()
    assert len(profiles) == 2
    labels = {p.label for p in profiles}
    assert labels == {"personal", "work"}


def test_get_profile_by_index(tmp_config_dir: Path) -> None:
    mgr = GeminiProfileManager()
    mgr.add_profile("alpha", "oauth")
    mgr.add_profile("beta", "apikey")
    # Profiles are sorted; alpha is index 1
    profile = mgr.get_profile("1")
    assert profile.label == "alpha"


def test_get_profile_by_label(tmp_config_dir: Path) -> None:
    mgr = GeminiProfileManager()
    mgr.add_profile("Work-Profile", "oauth")
    profile = mgr.get_profile("work-profile")  # case-insensitive
    assert profile.label == "Work-Profile"


def test_get_profile_not_found_raises(tmp_config_dir: Path) -> None:
    mgr = GeminiProfileManager()
    mgr.add_profile("only", "oauth")
    with pytest.raises(ProfileNotFoundError):
        mgr.get_profile("nonexistent")


def test_get_profile_index_out_of_range_raises(tmp_config_dir: Path) -> None:
    mgr = GeminiProfileManager()
    mgr.add_profile("only", "oauth")
    with pytest.raises(ProfileNotFoundError):
        mgr.get_profile("99")


def test_remove_profile(tmp_config_dir: Path) -> None:
    mgr = GeminiProfileManager()
    mgr.add_profile("temp", "oauth")
    assert len(mgr.list_profiles()) == 1
    mgr.remove_profile("temp")
    assert len(mgr.list_profiles()) == 0


def test_remove_active_profile_raises(
    tmp_config_dir: Path, fake_gemini_dir: Path
) -> None:

    mgr = GeminiProfileManager()
    profile = mgr.add_profile("active-profile", "apikey")
    key_file = profile.path / "api_key.txt"
    key_file.write_text("AIzaFakeKey\n", encoding="utf-8")

    with patch("switcher.auth.codex_auth.write_env_sh"):
        mgr.switch_to("active-profile")

    with pytest.raises(AuthError, match="Cannot remove active"):
        mgr.remove_profile("active-profile")


def test_switch_to_apikey_profile(tmp_config_dir: Path, fake_gemini_dir: Path) -> None:
    mgr = GeminiProfileManager()
    profile = mgr.add_profile("api-work", "apikey")
    (profile.path / "api_key.txt").write_text("AIzaTestKey123\n", encoding="utf-8")

    with patch("switcher.auth.codex_auth.write_env_sh") as mock_env:
        label = mgr.switch_to("api-work")

    assert label == "api-work"
    mock_env.assert_called_once_with(gemini_key="AIzaTestKey123", codex_key=None)


def test_switch_to_apikey_profile_preserves_codex_env_var(
    tmp_config_dir: Path, fake_gemini_dir: Path
) -> None:
    from switcher.utils import get_config_dir

    mgr = GeminiProfileManager()
    profile = mgr.add_profile("api-work", "apikey")
    (profile.path / "api_key.txt").write_text("AIzaTestKey123\n", encoding="utf-8")

    env_path = get_config_dir() / "env.sh"
    env_path.parent.mkdir(parents=True, exist_ok=True)
    env_path.write_text('export OPENAI_API_KEY="sk-codex-keep"\n', encoding="utf-8")

    label = mgr.switch_to("api-work")

    assert label == "api-work"
    content = env_path.read_text(encoding="utf-8")
    assert 'export GEMINI_API_KEY="AIzaTestKey123"' in content
    assert 'export GOOGLE_API_KEY="AIzaTestKey123"' in content
    assert 'export OPENAI_API_KEY="sk-codex-keep"' in content


def test_switch_to_oauth_profile(
    tmp_config_dir: Path, fake_gemini_dir: Path, sample_oauth_creds: dict
) -> None:
    mgr = GeminiProfileManager()
    profile = mgr.add_profile("oauth-work", "oauth")
    creds_path = profile.path / "oauth_creds.json"
    creds_path.write_text(json.dumps(sample_oauth_creds), encoding="utf-8")

    with patch("switcher.auth.gemini_auth.detect_keyring_mode", return_value="file"):
        label = mgr.switch_to("oauth-work")

    assert label == "oauth-work"
    symlink = fake_gemini_dir / "oauth_creds.json"
    assert symlink.is_symlink()


def test_switch_to_oauth_profile_clears_gemini_env_vars(
    tmp_config_dir: Path, fake_gemini_dir: Path, sample_oauth_creds: dict
) -> None:
    from switcher.utils import get_config_dir

    mgr = GeminiProfileManager()
    api_profile = mgr.add_profile("api-work", "apikey")
    (api_profile.path / "api_key.txt").write_text("AIzaTestKey123\n", encoding="utf-8")

    oauth_profile = mgr.add_profile("oauth-work", "oauth")
    (oauth_profile.path / "oauth_creds.json").write_text(
        json.dumps(sample_oauth_creds), encoding="utf-8"
    )

    env_path = get_config_dir() / "env.sh"
    env_path.parent.mkdir(parents=True, exist_ok=True)

    with patch("switcher.auth.codex_auth.write_env_sh"):
        mgr.switch_to("api-work")

    env_path.write_text(
        "\n".join(
            [
                '# Auto-generated by cli-switcher — do not edit manually',
                'export GEMINI_API_KEY="AIzaTestKey123"',
                'export GOOGLE_API_KEY="AIzaTestKey123"',
                'export OPENAI_API_KEY="sk-codex-keep"',
                "",
            ]
        ),
        encoding="utf-8",
    )

    with patch("switcher.auth.gemini_auth.detect_keyring_mode", return_value="file"):
        mgr.switch_to("oauth-work")

    content = env_path.read_text(encoding="utf-8")
    assert "GEMINI_API_KEY" not in content
    assert "GOOGLE_API_KEY" not in content
    assert 'export OPENAI_API_KEY="sk-codex-keep"' in content


def test_switch_next_rotates(
    tmp_config_dir: Path, fake_gemini_dir: Path, sample_oauth_creds: dict
) -> None:
    mgr = GeminiProfileManager()
    for label in ("first", "second"):
        p = mgr.add_profile(label, "oauth")
        (p.path / "oauth_creds.json").write_text(
            json.dumps(sample_oauth_creds), encoding="utf-8"
        )

    with patch("switcher.auth.gemini_auth.detect_keyring_mode", return_value="file"):
        mgr.switch_to("first")
        next_label = mgr.switch_next()

    assert next_label == "second"


def test_switch_next_requires_two_profiles(tmp_config_dir: Path) -> None:
    mgr = GeminiProfileManager()
    mgr.add_profile("lonely", "oauth")
    with pytest.raises(ProfileNotFoundError, match="at least 2"):
        mgr.switch_next()


def test_import_credentials_oauth(tmp_config_dir: Path, tmp_path: Path) -> None:
    creds_file = tmp_path / "oauth_creds.json"
    creds_file.write_text(
        json.dumps({"refreshToken": "rt", "token": {"refreshToken": "rt"}}),
        encoding="utf-8",
    )
    mgr = GeminiProfileManager()
    profile = mgr.import_credentials(creds_file, "imported")
    assert profile.auth_type == "oauth"
    assert (profile.path / "oauth_creds.json").exists()


def test_import_credentials_apikey(tmp_config_dir: Path, tmp_path: Path) -> None:
    key_file = tmp_path / "mykey.txt"
    key_file.write_text("AIzaFakeApiKey\n", encoding="utf-8")
    mgr = GeminiProfileManager()
    profile = mgr.import_credentials(key_file, "api-imported")
    assert profile.auth_type == "apikey"
    assert (profile.path / "api_key.txt").exists()


def test_import_credentials_file_not_found_raises(tmp_config_dir: Path) -> None:
    from pathlib import Path

    mgr = GeminiProfileManager()
    with pytest.raises(AuthError, match="File not found"):
        mgr.import_credentials(Path("/nonexistent/file.json"), "label")


def test_export_profile_to_directory(
    tmp_config_dir: Path, tmp_path: Path, sample_oauth_creds: dict
) -> None:
    mgr = GeminiProfileManager()
    profile = mgr.add_profile("export-me", "oauth")
    (profile.path / "oauth_creds.json").write_text(
        json.dumps(sample_oauth_creds), encoding="utf-8"
    )

    dest_dir = tmp_path / "exports"
    dest_dir.mkdir()
    out = mgr.export_profile("export-me", dest_dir)

    assert out.name == "export-me_oauth_creds.json"
    assert out.exists()
    exported = json.loads(out.read_text(encoding="utf-8"))
    assert exported["refreshToken"] == sample_oauth_creds["refreshToken"]


def test_active_profile_marked_in_list(
    tmp_config_dir: Path, fake_gemini_dir: Path, sample_oauth_creds: dict
) -> None:
    mgr = GeminiProfileManager()
    p = mgr.add_profile("active-one", "oauth")
    (p.path / "oauth_creds.json").write_text(
        json.dumps(sample_oauth_creds), encoding="utf-8"
    )
    mgr.add_profile("inactive", "oauth")

    with patch("switcher.auth.gemini_auth.detect_keyring_mode", return_value="file"):
        mgr.switch_to("active-one")

    profiles = mgr.list_profiles()
    active = [p for p in profiles if p.is_active]
    assert len(active) == 1
    assert active[0].label == "active-one"
