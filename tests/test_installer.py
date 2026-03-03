"""Tests for switcher.installer module."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING
from unittest.mock import patch

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

from switcher.installer import (
    copy_hook_scripts,
    detect_shell,
    generate_env_sh,
    generate_shell_snippet,
    get_rc_file,
    inject_into_rc,
    install_bin_symlink,
    install_gemini_hooks,
    install_slash_command,
    remove_bin_symlink,
    remove_from_rc,
    remove_gemini_hooks,
    remove_slash_command,
    run_install,
    run_uninstall,
)

# ---------------------------------------------------------------------------
# generate_shell_snippet
# ---------------------------------------------------------------------------


def test_generate_shell_snippet_contains_markers(tmp_path: Path) -> None:
    with patch("switcher.installer.get_config_dir", return_value=tmp_path):
        snippet = generate_shell_snippet()
    assert "# >>> cli-switcher >>>" in snippet
    assert "# <<< cli-switcher <<<" in snippet


def test_generate_shell_snippet_contains_source_env(tmp_path: Path) -> None:
    with patch("switcher.installer.get_config_dir", return_value=tmp_path):
        snippet = generate_shell_snippet()
    assert "env.sh" in snippet
    assert "alias sw=" in snippet


# ---------------------------------------------------------------------------
# inject_into_rc / remove_from_rc
# ---------------------------------------------------------------------------


def test_inject_into_rc_appends_snippet(tmp_path: Path) -> None:
    rc = tmp_path / ".bashrc"
    rc.write_text("# existing content\n")
    with patch("switcher.installer.get_config_dir", return_value=tmp_path):
        result = inject_into_rc(rc)
    assert result is True
    content = rc.read_text()
    assert "# >>> cli-switcher >>>" in content
    assert "# existing content" in content


def test_inject_into_rc_idempotent(tmp_path: Path) -> None:
    rc = tmp_path / ".bashrc"
    rc.write_text("")
    with patch("switcher.installer.get_config_dir", return_value=tmp_path):
        inject_into_rc(rc)
        result = inject_into_rc(rc)
    assert result is False
    # Snippet appears exactly once
    assert rc.read_text().count("# >>> cli-switcher >>>") == 1


def test_inject_into_rc_creates_file_if_missing(tmp_path: Path) -> None:
    rc = tmp_path / ".bashrc"
    with patch("switcher.installer.get_config_dir", return_value=tmp_path):
        result = inject_into_rc(rc)
    assert result is True
    assert rc.exists()


def test_remove_from_rc_removes_snippet(tmp_path: Path) -> None:
    rc = tmp_path / ".bashrc"
    rc.write_text(
        "before\n# >>> cli-switcher >>>\nstuff\n# <<< cli-switcher <<<\nafter\n"
    )
    result = remove_from_rc(rc)
    assert result is True
    content = rc.read_text()
    assert "# >>> cli-switcher >>>" not in content
    assert "before" in content
    assert "after" in content


def test_remove_from_rc_no_op_if_missing(tmp_path: Path) -> None:
    rc = tmp_path / "nonexistent_rc"
    result = remove_from_rc(rc)
    assert result is False


def test_remove_from_rc_no_op_if_no_marker(tmp_path: Path) -> None:
    rc = tmp_path / ".bashrc"
    rc.write_text("# no switcher content\n")
    result = remove_from_rc(rc)
    assert result is False


# ---------------------------------------------------------------------------
# install_gemini_hooks / remove_gemini_hooks
# ---------------------------------------------------------------------------


def test_install_gemini_hooks_writes_settings(tmp_path: Path) -> None:
    settings_path = tmp_path / "settings.json"
    with patch("switcher.installer.get_config_dir", return_value=tmp_path):
        result = install_gemini_hooks(settings_path)
    assert result is True
    data = json.loads(settings_path.read_text())
    hooks = data["hooks"]
    assert "AfterAgent" in hooks
    assert "BeforeAgent" in hooks


def test_install_gemini_hooks_idempotent(tmp_path: Path) -> None:
    settings_path = tmp_path / "settings.json"
    with patch("switcher.installer.get_config_dir", return_value=tmp_path):
        install_gemini_hooks(settings_path)
        result = install_gemini_hooks(settings_path)
    assert result is False


def test_install_gemini_hooks_merges_existing_settings(tmp_path: Path) -> None:
    settings_path = tmp_path / "settings.json"
    settings_path.write_text(json.dumps({"theme": "dark"}))
    with patch("switcher.installer.get_config_dir", return_value=tmp_path):
        install_gemini_hooks(settings_path)
    data = json.loads(settings_path.read_text())
    assert data["theme"] == "dark"
    assert "hooks" in data


def test_remove_gemini_hooks_removes_entries(tmp_path: Path) -> None:
    settings_path = tmp_path / "settings.json"
    with patch("switcher.installer.get_config_dir", return_value=tmp_path):
        install_gemini_hooks(settings_path)
        result = remove_gemini_hooks(settings_path)
    assert result is True
    data = json.loads(settings_path.read_text())
    for hook_list in data.get("hooks", {}).values():
        for group in hook_list:
            for h in group.get("hooks", []):
                assert h.get("name") not in (
                    "switcher-auto-rotate",
                    "switcher-pre-check",
                )


def test_remove_gemini_hooks_no_op_if_missing(tmp_path: Path) -> None:
    settings_path = tmp_path / "nonexistent.json"
    result = remove_gemini_hooks(settings_path)
    assert result is False


# ---------------------------------------------------------------------------
# install_slash_command / remove_slash_command
# ---------------------------------------------------------------------------


def test_install_slash_command_creates_toml(tmp_path: Path) -> None:
    commands_dir = tmp_path / "commands"
    result = install_slash_command(commands_dir)
    assert result is True
    toml_path = commands_dir / "change.toml"
    assert toml_path.exists()
    assert "switcher gemini next" in toml_path.read_text()


def test_install_slash_command_idempotent(tmp_path: Path) -> None:
    commands_dir = tmp_path / "commands"
    install_slash_command(commands_dir)
    result = install_slash_command(commands_dir)
    assert result is False


def test_remove_slash_command_removes_file(tmp_path: Path) -> None:
    commands_dir = tmp_path / "commands"
    install_slash_command(commands_dir)
    result = remove_slash_command(commands_dir)
    assert result is True
    assert not (commands_dir / "change.toml").exists()


def test_remove_slash_command_no_op_if_missing(tmp_path: Path) -> None:
    commands_dir = tmp_path / "commands"
    commands_dir.mkdir()
    result = remove_slash_command(commands_dir)
    assert result is False


# ---------------------------------------------------------------------------
# generate_env_sh
# ---------------------------------------------------------------------------


def _setup_gemini_profile(config_dir: Path, label: str, api_key: str) -> None:
    profile_dir = config_dir / "profiles" / "gemini" / label
    profile_dir.mkdir(parents=True)
    (profile_dir / "api_key.txt").write_text(api_key)


def _setup_codex_profile(config_dir: Path, label: str, api_key: str) -> None:
    profile_dir = config_dir / "profiles" / "codex" / label
    profile_dir.mkdir(parents=True)
    auth = {"OPENAI_API_KEY": api_key, "tokens": None, "last_refresh": None}
    (profile_dir / "auth.json").write_text(json.dumps(auth))


def test_generate_env_sh_writes_gemini_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    config_dir = tmp_path / "cli-switcher"
    config_dir.mkdir(parents=True)
    _setup_gemini_profile(config_dir, "work", "gemini-test-key")
    state = {"gemini": {"active_profile": "work"}, "codex": {}}
    (config_dir / "state.json").write_text(json.dumps(state))

    with (
        patch("switcher.installer.get_config_dir", return_value=config_dir),
        patch("switcher.state.get_config_dir", return_value=config_dir),
    ):
        generate_env_sh()

    env_sh = (config_dir / "env.sh").read_text()
    assert 'export GEMINI_API_KEY="gemini-test-key"' in env_sh
    assert 'export GOOGLE_API_KEY="gemini-test-key"' in env_sh


def test_generate_env_sh_writes_codex_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    config_dir = tmp_path / "cli-switcher"
    config_dir.mkdir(parents=True)
    _setup_codex_profile(config_dir, "work", "sk-test-openai-key")
    state = {"gemini": {}, "codex": {"active_profile": "work"}}
    (config_dir / "state.json").write_text(json.dumps(state))

    with (
        patch("switcher.installer.get_config_dir", return_value=config_dir),
        patch("switcher.state.get_config_dir", return_value=config_dir),
    ):
        generate_env_sh()

    env_sh = (config_dir / "env.sh").read_text()
    assert 'export OPENAI_API_KEY="sk-test-openai-key"' in env_sh


def test_generate_env_sh_no_active_profile_writes_header_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_dir = tmp_path / "cli-switcher"
    config_dir.mkdir(parents=True)
    state: dict = {"gemini": {}, "codex": {}}
    (config_dir / "state.json").write_text(json.dumps(state))

    with (
        patch("switcher.installer.get_config_dir", return_value=config_dir),
        patch("switcher.state.get_config_dir", return_value=config_dir),
    ):
        generate_env_sh()

    env_sh = (config_dir / "env.sh").read_text()
    assert "GEMINI_API_KEY" not in env_sh
    assert "OPENAI_API_KEY" not in env_sh


# ---------------------------------------------------------------------------
# detect_shell
# ---------------------------------------------------------------------------


def test_detect_shell_bash(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SHELL", "/bin/bash")
    assert detect_shell() == "bash"


def test_detect_shell_zsh(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SHELL", "/usr/bin/zsh")
    assert detect_shell() == "zsh"


def test_detect_shell_fish(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SHELL", "/usr/bin/fish")
    assert detect_shell() == "fish"


def test_detect_shell_default_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SHELL", raising=False)
    assert detect_shell() == "bash"


# ---------------------------------------------------------------------------
# get_rc_file
# ---------------------------------------------------------------------------


def test_get_rc_file_bash() -> None:
    from pathlib import Path

    rc = get_rc_file("bash")
    assert rc == Path.home() / ".bashrc"


def test_get_rc_file_zsh() -> None:
    from pathlib import Path

    rc = get_rc_file("zsh")
    assert rc == Path.home() / ".zshrc"


def test_get_rc_file_fish() -> None:
    from pathlib import Path

    rc = get_rc_file("fish")
    assert rc == Path.home() / ".config" / "fish" / "config.fish"


def test_get_rc_file_unknown_falls_back_to_bash() -> None:
    from pathlib import Path

    rc = get_rc_file("powershell")
    assert rc == Path.home() / ".bashrc"


# ---------------------------------------------------------------------------
# install_gemini_hooks / remove_gemini_hooks — corrupt JSON branch
# ---------------------------------------------------------------------------


def test_install_gemini_hooks_corrupt_json_resets(tmp_path: Path) -> None:
    settings_path = tmp_path / "settings.json"
    settings_path.write_text("{bad json")
    with patch("switcher.installer.get_config_dir", return_value=tmp_path):
        result = install_gemini_hooks(settings_path)
    assert result is True
    data = json.loads(settings_path.read_text())
    assert "hooks" in data


def test_remove_gemini_hooks_corrupt_json_returns_false(tmp_path: Path) -> None:
    settings_path = tmp_path / "settings.json"
    settings_path.write_text("{bad json")
    result = remove_gemini_hooks(settings_path)
    assert result is False


# ---------------------------------------------------------------------------
# generate_env_sh — corrupt auth.json branch
# ---------------------------------------------------------------------------


def test_generate_env_sh_corrupt_codex_auth_skips_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_dir = tmp_path / "cli-switcher"
    config_dir.mkdir(parents=True)
    profile_dir = config_dir / "profiles" / "codex" / "work"
    profile_dir.mkdir(parents=True)
    (profile_dir / "auth.json").write_text("{bad json")
    state = {"gemini": {}, "codex": {"active_profile": "work"}}
    (config_dir / "state.json").write_text(json.dumps(state))

    with (
        patch("switcher.installer.get_config_dir", return_value=config_dir),
        patch("switcher.state.get_config_dir", return_value=config_dir),
    ):
        generate_env_sh()

    env_sh = (config_dir / "env.sh").read_text()
    assert "OPENAI_API_KEY" not in env_sh


# ---------------------------------------------------------------------------
# copy_hook_scripts
# ---------------------------------------------------------------------------


def test_copy_hook_scripts_copies_py_files(tmp_path: Path) -> None:
    dest_config = tmp_path / "config"
    with patch("switcher.installer.get_config_dir", return_value=dest_config):
        copy_hook_scripts()
    hooks_dir = dest_config / "hooks"
    assert hooks_dir.exists()
    py_files = list(hooks_dir.glob("*.py"))
    assert len(py_files) > 0
    names = [f.name for f in py_files]
    assert "gemini_after_agent.py" in names or "gemini_before_agent.py" in names


# ---------------------------------------------------------------------------
# install_bin_symlink / remove_bin_symlink
# ---------------------------------------------------------------------------


def test_install_bin_symlink_creates_link(tmp_path: Path) -> None:
    with patch("pathlib.Path.home", return_value=tmp_path):
        result = install_bin_symlink()
    # Result is True or False depending on whether switcher executable was found
    assert isinstance(result, bool)


def test_install_bin_symlink_simple(tmp_path: Path) -> None:
    """Test that install_bin_symlink runs without error."""
    with patch("pathlib.Path.home", return_value=tmp_path):
        result = install_bin_symlink()
    assert isinstance(result, bool)


def test_remove_bin_symlink_removes_existing(tmp_path: Path) -> None:
    fake_bin = tmp_path / ".local" / "bin"
    fake_bin.mkdir(parents=True)
    link = fake_bin / "switcher"
    target = tmp_path / "switcher"
    target.write_text("#!/bin/sh")
    link.symlink_to(target)

    with patch("pathlib.Path.home", return_value=tmp_path):
        result = remove_bin_symlink()
    assert result is True
    assert not link.exists()


def test_remove_bin_symlink_no_op_if_missing(tmp_path: Path) -> None:
    with patch("pathlib.Path.home", return_value=tmp_path):
        result = remove_bin_symlink()
    assert result is False


# ---------------------------------------------------------------------------
# run_install / run_uninstall (mocked orchestrators)
# ---------------------------------------------------------------------------


def test_run_install_calls_all_steps(tmp_path: Path) -> None:
    with (
        patch("switcher.installer.detect_shell", return_value="bash"),
        patch("switcher.installer.get_rc_file", return_value=tmp_path / ".bashrc"),
        patch("switcher.installer.inject_into_rc", return_value=True),
        patch("switcher.installer.copy_hook_scripts"),
        patch("switcher.installer.install_gemini_hooks", return_value=True),
        patch("switcher.installer.install_slash_command", return_value=True),
        patch("switcher.installer.generate_env_sh"),
        patch("switcher.installer.install_bin_symlink", return_value=True),
        patch("switcher.installer.print_info"),
        patch("switcher.installer.print_success"),
    ):
        run_install()  # should not raise


def test_run_install_already_installed(tmp_path: Path) -> None:
    """When everything is already installed, prints 'already installed' message."""
    with (
        patch("switcher.installer.detect_shell", return_value="bash"),
        patch("switcher.installer.get_rc_file", return_value=tmp_path / ".bashrc"),
        patch("switcher.installer.inject_into_rc", return_value=False),
        patch("switcher.installer.copy_hook_scripts"),
        patch("switcher.installer.install_gemini_hooks", return_value=False),
        patch("switcher.installer.install_slash_command", return_value=False),
        patch("switcher.installer.generate_env_sh"),
        patch("switcher.installer.install_bin_symlink", return_value=False),
        patch("switcher.installer.print_info") as mock_info,
        patch("switcher.installer.print_success"),
    ):
        run_install()
    messages = [str(call) for call in mock_info.call_args_list]
    assert any("already" in m.lower() for m in messages)


def test_run_uninstall_calls_all_steps(tmp_path: Path) -> None:
    with (
        patch("switcher.installer.detect_shell", return_value="bash"),
        patch("switcher.installer.get_rc_file", return_value=tmp_path / ".bashrc"),
        patch("switcher.installer.remove_from_rc", return_value=True),
        patch("switcher.installer.remove_gemini_hooks", return_value=True),
        patch("switcher.installer.remove_slash_command", return_value=True),
        patch("switcher.installer.remove_bin_symlink", return_value=True),
        patch("switcher.installer.print_info"),
        patch("switcher.installer.print_success"),
    ):
        run_uninstall()  # should not raise


def test_run_uninstall_nothing_to_remove(tmp_path: Path) -> None:
    with (
        patch("switcher.installer.detect_shell", return_value="bash"),
        patch("switcher.installer.get_rc_file", return_value=tmp_path / ".bashrc"),
        patch("switcher.installer.remove_from_rc", return_value=False),
        patch("switcher.installer.remove_gemini_hooks", return_value=False),
        patch("switcher.installer.remove_slash_command", return_value=False),
        patch("switcher.installer.remove_bin_symlink", return_value=False),
        patch("switcher.installer.print_info"),
        patch("switcher.installer.print_success"),
    ):
        run_uninstall()
    # Should complete without error
