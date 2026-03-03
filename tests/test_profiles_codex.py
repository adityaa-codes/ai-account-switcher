"""Tests for CodexProfileManager."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

from switcher.errors import AuthError, ProfileNotFoundError
from switcher.profiles.codex import CodexProfileManager

if TYPE_CHECKING:
    from pathlib import Path


def test_list_profiles_empty(tmp_config_dir: Path) -> None:
    mgr = CodexProfileManager()
    assert mgr.list_profiles() == []


def test_add_profile_creates_directory_and_meta(tmp_config_dir: Path) -> None:
    mgr = CodexProfileManager()
    profile = mgr.add_profile("personal", "apikey")

    assert profile.label == "personal"
    assert profile.auth_type == "apikey"
    assert profile.path.is_dir()
    meta = json.loads((profile.path / "meta.json").read_text(encoding="utf-8"))
    assert meta["auth_type"] == "apikey"


def test_add_profile_chatgpt_creates_directory(tmp_config_dir: Path) -> None:
    mgr = CodexProfileManager()
    profile = mgr.add_profile("chatgpt-work", "chatgpt")
    assert profile.auth_type == "chatgpt"
    assert (profile.path / "meta.json").exists()


def test_add_profile_duplicate_raises(tmp_config_dir: Path) -> None:
    mgr = CodexProfileManager()
    mgr.add_profile("personal", "apikey")
    with pytest.raises(AuthError, match="already exists"):
        mgr.add_profile("personal", "apikey")


def test_list_profiles_returns_all(tmp_config_dir: Path) -> None:
    mgr = CodexProfileManager()
    mgr.add_profile("personal", "apikey")
    mgr.add_profile("work", "chatgpt")
    profiles = mgr.list_profiles()
    assert len(profiles) == 2
    labels = {p.label for p in profiles}
    assert labels == {"personal", "work"}


def test_get_profile_by_index(tmp_config_dir: Path) -> None:
    mgr = CodexProfileManager()
    mgr.add_profile("alpha", "apikey")
    mgr.add_profile("beta", "chatgpt")
    profile = mgr.get_profile("1")
    assert profile.label == "alpha"


def test_get_profile_by_label_case_insensitive(tmp_config_dir: Path) -> None:
    mgr = CodexProfileManager()
    mgr.add_profile("WorkProfile", "apikey")
    profile = mgr.get_profile("workprofile")
    assert profile.label == "WorkProfile"


def test_get_profile_not_found_raises(tmp_config_dir: Path) -> None:
    mgr = CodexProfileManager()
    mgr.add_profile("only", "apikey")
    with pytest.raises(ProfileNotFoundError):
        mgr.get_profile("nonexistent")


def test_remove_profile(tmp_config_dir: Path) -> None:
    mgr = CodexProfileManager()
    mgr.add_profile("temp", "apikey")
    mgr.remove_profile("temp")
    assert len(mgr.list_profiles()) == 0


def test_remove_active_profile_raises(
    tmp_config_dir: Path, fake_codex_dir: Path, sample_auth_json: dict
) -> None:
    mgr = CodexProfileManager()
    profile = mgr.add_profile("active-one", "apikey")
    (profile.path / "auth.json").write_text(
        json.dumps(sample_auth_json), encoding="utf-8"
    )

    with patch("switcher.auth.codex_auth.write_env_sh"):
        mgr.switch_to("active-one")

    with pytest.raises(AuthError, match="Cannot remove active"):
        mgr.remove_profile("active-one")


def test_switch_to_apikey_profile(
    tmp_config_dir: Path, fake_codex_dir: Path, sample_auth_json: dict
) -> None:
    mgr = CodexProfileManager()
    profile = mgr.add_profile("api-personal", "apikey")
    (profile.path / "auth.json").write_text(
        json.dumps(sample_auth_json), encoding="utf-8"
    )

    with patch("switcher.auth.codex_auth.write_env_sh") as mock_env:
        label = mgr.switch_to("api-personal")

    assert label == "api-personal"
    symlink = fake_codex_dir / "auth.json"
    assert symlink.is_symlink()
    mock_env.assert_called_once()


def test_switch_to_chatgpt_profile(
    tmp_config_dir: Path, fake_codex_dir: Path, sample_chatgpt_auth_json: dict
) -> None:
    mgr = CodexProfileManager()
    profile = mgr.add_profile("chatgpt-personal", "chatgpt")
    (profile.path / "auth.json").write_text(
        json.dumps(sample_chatgpt_auth_json), encoding="utf-8"
    )

    label = mgr.switch_to("chatgpt-personal")

    assert label == "chatgpt-personal"
    symlink = fake_codex_dir / "auth.json"
    assert symlink.is_symlink()


def test_switch_next_rotates(
    tmp_config_dir: Path, fake_codex_dir: Path, sample_auth_json: dict
) -> None:
    mgr = CodexProfileManager()
    for name in ("first", "second"):
        p = mgr.add_profile(name, "apikey")
        (p.path / "auth.json").write_text(
            json.dumps(sample_auth_json), encoding="utf-8"
        )

    with patch("switcher.auth.codex_auth.write_env_sh"):
        mgr.switch_to("first")
        next_label = mgr.switch_next()

    assert next_label == "second"


def test_switch_next_requires_two_profiles(tmp_config_dir: Path) -> None:
    mgr = CodexProfileManager()
    mgr.add_profile("lonely", "apikey")
    with pytest.raises(ProfileNotFoundError, match="at least 2"):
        mgr.switch_next()


def test_import_credentials_apikey(
    tmp_config_dir: Path, tmp_path: Path, sample_auth_json: dict
) -> None:
    auth_file = tmp_path / "auth.json"
    auth_file.write_text(json.dumps(sample_auth_json), encoding="utf-8")

    mgr = CodexProfileManager()
    profile = mgr.import_credentials(auth_file, "imported-api")

    assert profile.auth_type == "apikey"
    assert (profile.path / "auth.json").exists()


def test_import_plain_api_key_creates_auth_json(
    tmp_config_dir: Path, tmp_path: Path
) -> None:
    key_file = tmp_path / "key.txt"
    key_file.write_text("sk-test-key-12345\n", encoding="utf-8")

    mgr = CodexProfileManager()
    profile = mgr.import_credentials(key_file, "plain-key")

    auth = json.loads((profile.path / "auth.json").read_text(encoding="utf-8"))
    assert auth.get("OPENAI_API_KEY") == "sk-test-key-12345"


def test_import_credentials_file_not_found_raises(tmp_config_dir: Path) -> None:
    from pathlib import Path as PathType

    mgr = CodexProfileManager()
    with pytest.raises(AuthError, match="File not found"):
        mgr.import_credentials(PathType("/nonexistent/auth.json"), "label")


def test_export_profile_to_directory(
    tmp_config_dir: Path, tmp_path: Path, sample_auth_json: dict
) -> None:
    mgr = CodexProfileManager()
    profile = mgr.add_profile("export-me", "apikey")
    (profile.path / "auth.json").write_text(
        json.dumps(sample_auth_json), encoding="utf-8"
    )

    dest_dir = tmp_path / "exports"
    dest_dir.mkdir()
    out = mgr.export_profile("export-me", dest_dir)

    assert out.name == "export-me_auth.json"
    assert out.exists()
    exported = json.loads(out.read_text(encoding="utf-8"))
    assert exported["OPENAI_API_KEY"] == sample_auth_json["OPENAI_API_KEY"]


def test_active_profile_marked_in_list(
    tmp_config_dir: Path, fake_codex_dir: Path, sample_auth_json: dict
) -> None:
    mgr = CodexProfileManager()
    p = mgr.add_profile("active", "apikey")
    (p.path / "auth.json").write_text(json.dumps(sample_auth_json), encoding="utf-8")
    mgr.add_profile("idle", "apikey")

    with patch("switcher.auth.codex_auth.write_env_sh"):
        mgr.switch_to("active")

    profiles = mgr.list_profiles()
    active = [p for p in profiles if p.is_active]
    assert len(active) == 1
    assert active[0].label == "active"


# ---------------------------------------------------------------------------
# write_env_sh (codex_auth)
# ---------------------------------------------------------------------------


def test_write_env_sh_writes_gemini_key(tmp_path: Path) -> None:
    from switcher.auth.codex_auth import write_env_sh

    env_path = tmp_path / "env.sh"
    with patch("switcher.auth.codex_auth.get_config_dir", return_value=tmp_path):
        write_env_sh(gemini_key="g-key-123", codex_key=None)
    content = env_path.read_text()
    assert 'export GEMINI_API_KEY="g-key-123"' in content
    assert 'export GOOGLE_API_KEY="g-key-123"' in content


def test_write_env_sh_writes_codex_key(tmp_path: Path) -> None:
    from switcher.auth.codex_auth import write_env_sh

    env_path = tmp_path / "env.sh"
    with patch("switcher.auth.codex_auth.get_config_dir", return_value=tmp_path):
        write_env_sh(gemini_key=None, codex_key="sk-openai-456")
    content = env_path.read_text()
    assert 'export OPENAI_API_KEY="sk-openai-456"' in content


def test_write_env_sh_preserves_existing_gemini(tmp_path: Path) -> None:
    from switcher.auth.codex_auth import write_env_sh

    env_path = tmp_path / "env.sh"
    env_path.write_text('export GEMINI_API_KEY="existing-gemini"\n', encoding="utf-8")

    with patch("switcher.auth.codex_auth.get_config_dir", return_value=tmp_path):
        write_env_sh(gemini_key=None, codex_key="sk-new-codex")

    content = env_path.read_text()
    assert 'export GEMINI_API_KEY="existing-gemini"' in content
    assert 'export OPENAI_API_KEY="sk-new-codex"' in content


def test_write_env_sh_both_keys(tmp_path: Path) -> None:
    from switcher.auth.codex_auth import write_env_sh

    env_path = tmp_path / "env.sh"
    with patch("switcher.auth.codex_auth.get_config_dir", return_value=tmp_path):
        write_env_sh(gemini_key="g-key", codex_key="sk-key")
    content = env_path.read_text()
    assert "GEMINI_API_KEY" in content
    assert "OPENAI_API_KEY" in content


def test_activate_chatgpt_profile_missing_auth_raises(
    fake_codex_dir: Path, tmp_config_dir: Path
) -> None:
    import pytest

    from switcher.auth.codex_auth import activate_chatgpt_profile
    from switcher.errors import AuthError

    with pytest.raises(AuthError, match=r"Missing auth\.json"):
        activate_chatgpt_profile(tmp_config_dir / "nonexistent_profile")
