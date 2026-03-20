"""Tests for switcher.cli module."""

from __future__ import annotations

import argparse
import json
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

from switcher.cli import (
    _dispatch,
    _print_config,
    _profile_has_oauth_creds,
    _recover_profile_oauth_from_profile_keyring_backup,
    build_parser,
    cmd_add,
    cmd_config,
    cmd_export,
    cmd_health,
    cmd_import,
    cmd_list,
    cmd_next,
    cmd_remove,
    cmd_status,
    cmd_switch,
    cmd_version,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_profile(
    tmp_path: Path,
    label: str = "work",
    auth_type: str = "oauth",
    *,
    oauth_creds: dict | None = None,
) -> MagicMock:
    """Return a mock Profile object with a real directory."""
    profile_dir = tmp_path / label
    profile_dir.mkdir(parents=True, exist_ok=True)

    profile = MagicMock()
    profile.label = label
    profile.auth_type = auth_type
    profile.path = profile_dir
    profile.meta = {}

    if oauth_creds is not None:
        creds_file = profile_dir / "oauth_creds.json"
        creds_file.write_text(json.dumps(oauth_creds), encoding="utf-8")

    return profile


def _make_manager(profiles: list[MagicMock], active: str | None = None) -> MagicMock:
    """Return a mock ProfileManager."""
    mgr = MagicMock()
    mgr.list_profiles.return_value = profiles
    mgr.get_profile.side_effect = lambda label: next(
        (p for p in profiles if p.label == label),
        profiles[0] if profiles else None,
    )
    mgr.switch_to.return_value = active or (profiles[0].label if profiles else "")
    mgr.switch_next.return_value = profiles[1].label if len(profiles) > 1 else "next"
    return mgr


# ---------------------------------------------------------------------------
# _profile_has_oauth_creds
# ---------------------------------------------------------------------------


def test_profile_has_oauth_creds_missing_file(tmp_path: Path) -> None:
    profile = _make_profile(tmp_path)
    assert _profile_has_oauth_creds(profile) is False


def test_profile_has_oauth_creds_corrupt_json(tmp_path: Path) -> None:
    profile = _make_profile(tmp_path)
    (profile.path / "oauth_creds.json").write_text("{bad json")
    assert _profile_has_oauth_creds(profile) is False


def test_profile_has_oauth_creds_flat_refresh_token(tmp_path: Path) -> None:
    creds = {"refresh_token": "rt-abc", "access_token": "at-abc"}
    profile = _make_profile(tmp_path, oauth_creds=creds)
    assert _profile_has_oauth_creds(profile) is True


def test_profile_has_oauth_creds_nested_token(tmp_path: Path) -> None:
    creds = {"token": {"refreshToken": "rt-abc", "accessToken": "at-abc"}}
    profile = _make_profile(tmp_path, oauth_creds=creds)
    assert _profile_has_oauth_creds(profile) is True


def test_profile_has_oauth_creds_empty_token(tmp_path: Path) -> None:
    creds = {"token": {}}
    profile = _make_profile(tmp_path, oauth_creds=creds)
    assert _profile_has_oauth_creds(profile) is False


# ---------------------------------------------------------------------------
# _recover_profile_oauth_from_profile_keyring_backup
# ---------------------------------------------------------------------------


def test_recover_from_keyring_backup_missing_file(tmp_path: Path) -> None:
    profile = _make_profile(tmp_path)
    assert _recover_profile_oauth_from_profile_keyring_backup(profile) is False


def test_recover_from_keyring_backup_corrupt_json(tmp_path: Path) -> None:
    profile = _make_profile(tmp_path)
    (profile.path / "keyring_creds.json").write_text("{bad json")
    assert _recover_profile_oauth_from_profile_keyring_backup(profile) is False


def test_recover_from_keyring_backup_valid(tmp_path: Path) -> None:
    profile = _make_profile(tmp_path)
    # convert_from_keyring_format expects nested {"token": {...}} format
    keyring_payload = {
        "token": {
            "refreshToken": "rt-abc",
            "accessToken": "at-abc",
            "expiresAt": 9999999999,
        }
    }
    (profile.path / "keyring_creds.json").write_text(json.dumps(keyring_payload))

    result = _recover_profile_oauth_from_profile_keyring_backup(profile)
    assert result is True
    written = json.loads((profile.path / "oauth_creds.json").read_text())
    assert written.get("refreshToken") == "rt-abc"


# ---------------------------------------------------------------------------
# build_parser
# ---------------------------------------------------------------------------


def test_build_parser_returns_parser() -> None:
    parser = build_parser()
    assert isinstance(parser, argparse.ArgumentParser)


def test_build_parser_version_command() -> None:
    parser = build_parser()
    args = parser.parse_args(["version"])
    assert args.command == "version"


def test_build_parser_gemini_list() -> None:
    parser = build_parser()
    args = parser.parse_args(["gemini", "list"])
    assert args.command == "gemini"
    assert args.action == "list"


def test_build_parser_gemini_switch() -> None:
    parser = build_parser()
    args = parser.parse_args(["gemini", "switch", "work"])
    assert args.command == "gemini"
    assert args.action == "switch"
    assert args.target == "work"


def test_build_parser_codex_next() -> None:
    parser = build_parser()
    args = parser.parse_args(["codex", "next"])
    assert args.command == "codex"
    assert args.action == "next"


def test_build_parser_config_key_value() -> None:
    parser = build_parser()
    args = parser.parse_args(["config", "general.log_level", "debug"])
    assert args.command == "config"
    assert args.key == "general.log_level"
    assert args.value == "debug"


# ---------------------------------------------------------------------------
# cmd_version
# ---------------------------------------------------------------------------


def test_cmd_version_prints_version(capsys: pytest.CaptureFixture) -> None:
    from switcher import __version__

    cmd_version(argparse.Namespace())
    captured = capsys.readouterr()
    assert __version__ in captured.out


# ---------------------------------------------------------------------------
# cmd_status
# ---------------------------------------------------------------------------


def test_cmd_status_calls_dashboard(tmp_path: Path) -> None:
    profiles = [_make_profile(tmp_path, "work", "oauth")]
    mgr = _make_manager(profiles)

    with (
        patch("switcher.cli.GeminiProfileManager", return_value=mgr),
        patch("switcher.cli.CodexProfileManager", return_value=mgr),
        patch("switcher.cli.get_active_profile", return_value="work"),
        patch(
            "switcher.cli.load_config",
            return_value={
                "auto_rotate": {"enabled": True},
                "general": {"log_level": "info"},
            },
        ),
        patch("switcher.cli.print_dashboard") as mock_dash,
    ):
        cmd_status(argparse.Namespace())
    mock_dash.assert_called_once()


# ---------------------------------------------------------------------------
# cmd_list
# ---------------------------------------------------------------------------


def test_cmd_list_calls_print_profile_list(tmp_path: Path) -> None:
    profiles = [_make_profile(tmp_path, "work", "apikey")]
    mgr = _make_manager(profiles, active="work")

    with (
        patch("switcher.cli.GeminiProfileManager", return_value=mgr),
        patch("switcher.cli.get_active_profile", return_value="work"),
        patch("switcher.cli.print_profile_list") as mock_list,
    ):
        cmd_list(argparse.Namespace(), "gemini")
    mock_list.assert_called_once()


# ---------------------------------------------------------------------------
# cmd_next
# ---------------------------------------------------------------------------


def test_cmd_next_calls_switch_next(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    profiles = [
        _make_profile(tmp_path, "work", "apikey"),
        _make_profile(tmp_path / "b", "personal", "apikey"),
    ]
    mgr = _make_manager(profiles, active="personal")

    with (
        patch("switcher.cli.GeminiProfileManager", return_value=mgr),
        patch("switcher.cli.print_success") as mock_ok,
    ):
        cmd_next(argparse.Namespace(), "gemini")
    mgr.switch_next.assert_called_once()
    mock_ok.assert_called_once()


# ---------------------------------------------------------------------------
# cmd_switch
# ---------------------------------------------------------------------------


def test_cmd_switch_apikey_profile(tmp_path: Path) -> None:
    profile = _make_profile(tmp_path, "work", "apikey")
    mgr = _make_manager([profile], active="work")

    with (
        patch("switcher.cli.GeminiProfileManager", return_value=mgr),
        patch("switcher.cli.print_success") as mock_ok,
    ):
        cmd_switch(argparse.Namespace(target="work"), "gemini")
    mgr.switch_to.assert_called_once_with("work")
    mock_ok.assert_called_once()


def test_cmd_switch_oauth_with_creds(tmp_path: Path) -> None:
    creds = {"token": {"refreshToken": "rt", "accessToken": "at"}}
    profile = _make_profile(tmp_path, "work", "oauth", oauth_creds=creds)
    mgr = _make_manager([profile], active="work")

    with (
        patch("switcher.cli.GeminiProfileManager", return_value=mgr),
        patch("switcher.cli.print_success"),
        patch("switcher.cli.print_info"),
    ):
        cmd_switch(argparse.Namespace(target="work"), "gemini")
    mgr.switch_to.assert_called_once_with("work")


def test_cmd_switch_oauth_no_creds_user_cancels(tmp_path: Path) -> None:
    profile = _make_profile(tmp_path, "work", "oauth")  # no creds file
    mgr = _make_manager([profile])

    with (
        patch("switcher.cli.GeminiProfileManager", return_value=mgr),
        patch(
            "switcher.cli._recover_profile_oauth_from_profile_keyring_backup",
            return_value=False,
        ),
        patch("switcher.cli._recover_profile_oauth_from_keyring", return_value=False),
        patch("switcher.cli.confirm", return_value=False),
        patch("switcher.cli.print_info"),
        patch("switcher.cli.print_warning"),
    ):
        cmd_switch(argparse.Namespace(target="work"), "gemini")
    mgr.switch_to.assert_not_called()


# ---------------------------------------------------------------------------
# cmd_remove
# ---------------------------------------------------------------------------


def test_cmd_remove_confirmed(tmp_path: Path) -> None:
    profile = _make_profile(tmp_path, "work")
    mgr = _make_manager([profile])
    mgr.remove_profile.return_value = "work"

    with (
        patch("switcher.cli.GeminiProfileManager", return_value=mgr),
        patch("switcher.cli.confirm", return_value=True),
        patch("switcher.cli.print_success") as mock_ok,
    ):
        cmd_remove(argparse.Namespace(target="work"), "gemini")
    mgr.remove_profile.assert_called_once_with("work")
    mock_ok.assert_called_once()


def test_cmd_remove_cancelled(tmp_path: Path) -> None:
    profile = _make_profile(tmp_path, "work")
    mgr = _make_manager([profile])

    with (
        patch("switcher.cli.GeminiProfileManager", return_value=mgr),
        patch("switcher.cli.confirm", return_value=False),
        patch("switcher.cli.print_info") as mock_info,
    ):
        cmd_remove(argparse.Namespace(target="work"), "gemini")
    mgr.remove_profile.assert_not_called()
    mock_info.assert_called()


# ---------------------------------------------------------------------------
# cmd_import
# ---------------------------------------------------------------------------


def test_cmd_import_calls_manager(tmp_path: Path) -> None:
    src = tmp_path / "creds.json"
    src.write_text('{"OPENAI_API_KEY": "sk-test"}')
    profile = _make_profile(tmp_path / "p", "creds", "apikey")
    mgr = _make_manager([profile])
    mgr.import_credentials.return_value = profile

    with (
        patch("switcher.cli.CodexProfileManager", return_value=mgr),
        patch("switcher.cli.print_success") as mock_ok,
    ):
        cmd_import(argparse.Namespace(path=str(src), label="creds"), "codex")
    mgr.import_credentials.assert_called_once()
    mock_ok.assert_called_once()


def test_cmd_import_uses_stem_as_label_when_missing(tmp_path: Path) -> None:
    src = tmp_path / "work_creds.json"
    src.write_text('{"OPENAI_API_KEY": "sk-test"}')
    profile = _make_profile(tmp_path / "p", "work_creds", "apikey")
    mgr = _make_manager([profile])
    mgr.import_credentials.return_value = profile

    with (
        patch("switcher.cli.CodexProfileManager", return_value=mgr),
        patch("switcher.cli.print_success"),
    ):
        cmd_import(argparse.Namespace(path=str(src), label=None), "codex")
    call_args = mgr.import_credentials.call_args
    assert call_args[0][1] == "work_creds"


# ---------------------------------------------------------------------------
# cmd_export
# ---------------------------------------------------------------------------


def test_cmd_export_calls_manager(tmp_path: Path) -> None:
    profile = _make_profile(tmp_path, "work")
    mgr = _make_manager([profile])
    mgr.export_profile.return_value = tmp_path / "work.json"

    with (
        patch("switcher.cli.GeminiProfileManager", return_value=mgr),
        patch("switcher.cli.print_success") as mock_ok,
    ):
        cmd_export(argparse.Namespace(target="work", dest=str(tmp_path)), "gemini")
    mgr.export_profile.assert_called_once()
    mock_ok.assert_called_once()


# ---------------------------------------------------------------------------
# cmd_health
# ---------------------------------------------------------------------------


def test_cmd_health_no_profiles(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    mgr = _make_manager([])

    with (
        patch("switcher.cli.GeminiProfileManager", return_value=mgr),
        patch("switcher.cli.print_warning") as mock_warn,
    ):
        cmd_health(argparse.Namespace(), "gemini")
    mock_warn.assert_called_once()


def test_cmd_health_with_profiles(tmp_path: Path) -> None:
    profile = _make_profile(tmp_path, "work", "apikey")
    mgr = _make_manager([profile])

    with (
        patch("switcher.cli.GeminiProfileManager", return_value=mgr),
        patch(
            "switcher.health.check_all_profiles",
            return_value=[(profile, "valid", "OK", None)],
        ),
        patch("switcher.cli.print_info"),
        patch("switcher.ui.print_table") as mock_table,
    ):
        cmd_health(argparse.Namespace(), "gemini")
    mock_table.assert_called_once()


# ---------------------------------------------------------------------------
# cmd_config
# ---------------------------------------------------------------------------


def test_cmd_config_no_key_prints_all(capsys: pytest.CaptureFixture) -> None:
    config = {"general": {"log_level": "info"}, "auto_rotate": {"enabled": True}}
    with patch("switcher.cli.load_config", return_value=config):
        cmd_config(argparse.Namespace(key=None, value=None, extra=[]))
    out = capsys.readouterr().out
    assert "log_level" in out


def test_cmd_config_get_existing_key(capsys: pytest.CaptureFixture) -> None:
    with patch("switcher.cli.get_config_value", return_value="info"):
        cmd_config(argparse.Namespace(key="get", value="general.log_level", extra=[]))
    out = capsys.readouterr().out
    assert "info" in out


def test_cmd_config_get_missing_args(capsys: pytest.CaptureFixture) -> None:
    with patch("switcher.cli.print_error") as mock_err:
        cmd_config(argparse.Namespace(key="get", value=None, extra=[]))
    mock_err.assert_called_once()


def test_cmd_config_set_value(capsys: pytest.CaptureFixture) -> None:
    with (
        patch("switcher.cli.set_config_value") as mock_set,
        patch("switcher.cli.print_success") as mock_ok,
    ):
        cmd_config(
            argparse.Namespace(key="set", value="general.log_level", extra=["debug"])
        )
    mock_set.assert_called_once_with("general.log_level", "debug")
    mock_ok.assert_called_once()


def test_cmd_config_set_missing_args() -> None:
    with patch("switcher.cli.print_error") as mock_err:
        cmd_config(argparse.Namespace(key="set", value=None, extra=[]))
    mock_err.assert_called_once()


def test_cmd_config_legacy_get(capsys: pytest.CaptureFixture) -> None:
    with patch("switcher.cli.get_config_value", return_value=True):
        cmd_config(argparse.Namespace(key="auto_rotate.enabled", value=None, extra=[]))
    out = capsys.readouterr().out
    assert "auto_rotate.enabled" in out


def test_cmd_config_legacy_set() -> None:
    with (
        patch("switcher.cli.set_config_value") as mock_set,
        patch("switcher.cli.print_success"),
    ):
        cmd_config(
            argparse.Namespace(key="auto_rotate.enabled", value="false", extra=[])
        )
    mock_set.assert_called_once_with("auto_rotate.enabled", "false")


# ---------------------------------------------------------------------------
# _print_config
# ---------------------------------------------------------------------------


def test_print_config_flat(capsys: pytest.CaptureFixture) -> None:
    _print_config({"key": "value"})
    out = capsys.readouterr().out
    assert "key" in out
    assert "value" in out


def test_print_config_nested(capsys: pytest.CaptureFixture) -> None:
    _print_config({"section": {"key": "value"}})
    out = capsys.readouterr().out
    assert "section.key" in out


# ---------------------------------------------------------------------------
# _dispatch
# ---------------------------------------------------------------------------


def test_dispatch_no_command_calls_status() -> None:
    parser = build_parser()
    with patch("switcher.cli.cmd_status") as mock_status:
        _dispatch(parser, argparse.Namespace(command=None))
    mock_status.assert_called_once()


def test_dispatch_status_command() -> None:
    parser = build_parser()
    with patch("switcher.cli.cmd_status") as mock_status:
        _dispatch(parser, argparse.Namespace(command="status"))
    mock_status.assert_called_once()


def test_dispatch_version_command() -> None:
    parser = build_parser()
    with patch("switcher.cli.cmd_version") as mock_ver:
        _dispatch(parser, argparse.Namespace(command="version"))
    mock_ver.assert_called_once()


def test_dispatch_install_command() -> None:
    parser = build_parser()
    with patch("switcher.cli.cmd_install") as mock_inst:
        _dispatch(parser, argparse.Namespace(command="install"))
    mock_inst.assert_called_once()


def test_dispatch_uninstall_command() -> None:
    parser = build_parser()
    with patch("switcher.cli.cmd_uninstall") as mock_uninst:
        _dispatch(parser, argparse.Namespace(command="uninstall"))
    mock_uninst.assert_called_once()


def test_dispatch_setup_command() -> None:
    parser = build_parser()
    with patch("switcher.cli.cmd_setup") as mock_setup:
        _dispatch(parser, argparse.Namespace(command="setup"))
    mock_setup.assert_called_once()


def test_cmd_setup_imports_discovered_credentials(
    capsys: pytest.CaptureFixture,
) -> None:
    from pathlib import Path

    from switcher.cli import cmd_setup
    from switcher.discovery import AuthDiscoveryResult

    gm_result = AuthDiscoveryResult(
        cli_name="gemini",
        path=Path("/tmp/gm/oauth_creds.json"),
        found=True,
        valid=True,
        reason="ok",
        detected_auth_type="oauth",
    )
    cx_result = AuthDiscoveryResult(
        cli_name="codex",
        path=Path("/tmp/cx/auth.json"),
        found=False,
        valid=False,
        reason="not found",
        detected_auth_type=None,
    )

    imported_profile = MagicMock()
    imported_profile.label = "personal-gemini"

    with (
        patch("switcher.installer.run_install"),
        patch(
            "switcher.discovery.discover_existing_auth",
            return_value={"gemini": gm_result, "codex": cx_result},
        ),
        patch("switcher.cli._get_manager") as mock_get_mgr,
        patch(
            "switcher.discovery.adopt_discovered_auth",
            side_effect=[imported_profile],
        ),
    ):
        mock_get_mgr.return_value = MagicMock()
        cmd_setup(argparse.Namespace(adopt=True, no_install=False))

    out = capsys.readouterr().out
    assert "Setup complete" in out
    assert "personal-gemini" in out
    assert "codex: not found" in out


def test_cmd_setup_fresh_mode_skips_adoption(capsys: pytest.CaptureFixture) -> None:
    from switcher.cli import cmd_setup

    with (
        patch("switcher.installer.run_install") as mock_install,
        patch("switcher.discovery.discover_existing_auth") as mock_discover,
    ):
        cmd_setup(argparse.Namespace(adopt=False, no_install=False))

    out = capsys.readouterr().out
    assert "Fresh setup mode" in out
    mock_install.assert_called_once()
    mock_discover.assert_not_called()


def test_cmd_setup_no_install_mode(capsys: pytest.CaptureFixture) -> None:
    from pathlib import Path

    from switcher.cli import cmd_setup
    from switcher.discovery import AuthDiscoveryResult

    gm_result = AuthDiscoveryResult(
        cli_name="gemini",
        path=Path("/tmp/gm/oauth_creds.json"),
        found=False,
        valid=False,
        reason="not found",
        detected_auth_type=None,
    )
    cx_result = AuthDiscoveryResult(
        cli_name="codex",
        path=Path("/tmp/cx/auth.json"),
        found=False,
        valid=False,
        reason="not found",
        detected_auth_type=None,
    )

    with (
        patch("switcher.installer.run_install") as mock_install,
        patch(
            "switcher.discovery.discover_existing_auth",
            return_value={"gemini": gm_result, "codex": cx_result},
        ),
    ):
        cmd_setup(argparse.Namespace(adopt=True, no_install=True))

    out = capsys.readouterr().out
    assert "Skipping install step" in out
    mock_install.assert_not_called()


def test_dispatch_gemini_list() -> None:
    parser = build_parser()
    mock_list = MagicMock()
    with patch.dict("switcher.cli._CLI_ACTIONS", {"list": mock_list}):
        _dispatch(parser, argparse.Namespace(command="gemini", action="list"))
    mock_list.assert_called_once()


def test_dispatch_codex_next() -> None:
    parser = build_parser()
    mock_next = MagicMock()
    with patch.dict("switcher.cli._CLI_ACTIONS", {"next": mock_next}):
        _dispatch(parser, argparse.Namespace(command="codex", action="next"))
    mock_next.assert_called_once()


def test_dispatch_gemini_no_action_calls_list() -> None:
    parser = build_parser()
    with patch("switcher.cli.cmd_list") as mock_list:
        _dispatch(parser, argparse.Namespace(command="gemini", action=None))
    mock_list.assert_called_once()


def test_dispatch_unknown_action_calls_help() -> None:
    parser = build_parser()
    with patch.object(parser, "print_help") as mock_help:
        _dispatch(parser, argparse.Namespace(command="gemini", action="unknown"))
    mock_help.assert_called_once()


def test_dispatch_unknown_command_calls_help() -> None:
    parser = build_parser()
    with patch.object(parser, "print_help") as mock_help:
        _dispatch(parser, argparse.Namespace(command="unknown"))
    mock_help.assert_called_once()


# ---------------------------------------------------------------------------
# SwitcherError bubbles to main()
# ---------------------------------------------------------------------------


def test_main_catches_switcher_error(tmp_path: Path) -> None:
    from switcher.cli import main
    from switcher.errors import SwitcherError

    with (
        patch("switcher.cli.ensure_dirs"),
        patch(
            "switcher.cli.load_config",
            return_value={"general": {"log_level": "info"}},
        ),
        patch("switcher.cli.setup_logging"),
        patch("switcher.cli._dispatch", side_effect=SwitcherError("test error")),
        patch("switcher.cli.print_error") as mock_err,
        patch("sys.argv", ["switcher", "version"]),
    ):
        try:
            main()
        except SystemExit as exc:
            assert exc.code == 1
    mock_err.assert_called_once()


# ---------------------------------------------------------------------------
# cmd_add
# ---------------------------------------------------------------------------


def test_cmd_add_gemini_apikey(tmp_path: Path) -> None:
    profile = _make_profile(tmp_path, "work", "apikey")
    mgr = _make_manager([profile])
    mgr.add_profile.return_value = profile

    with (
        patch("switcher.cli.GeminiProfileManager", return_value=mgr),
        patch("switcher.cli.print_success") as mock_ok,
        patch("switcher.cli.print_info"),
    ):
        cmd_add(argparse.Namespace(label="work", type="apikey"), "gemini")
    mgr.add_profile.assert_called_once_with("work", "apikey")
    mock_ok.assert_called_once()


def test_cmd_add_codex_apikey(tmp_path: Path) -> None:
    profile = _make_profile(tmp_path, "work", "apikey")
    mgr = _make_manager([profile])
    mgr.add_profile.return_value = profile

    with (
        patch("switcher.cli.CodexProfileManager", return_value=mgr),
        patch("switcher.cli.print_success"),
        patch("switcher.cli.print_info"),
    ):
        cmd_add(argparse.Namespace(label="work", type="apikey"), "codex")
    mgr.add_profile.assert_called_once_with("work", "apikey")


def test_cmd_add_codex_chatgpt(tmp_path: Path) -> None:
    profile = _make_profile(tmp_path, "work", "chatgpt")
    mgr = _make_manager([profile])
    mgr.add_profile.return_value = profile

    with (
        patch("switcher.cli.CodexProfileManager", return_value=mgr),
        patch("switcher.cli.print_success"),
        patch("switcher.cli.print_info"),
    ):
        cmd_add(argparse.Namespace(label="work", type="chatgpt"), "codex")
    mgr.add_profile.assert_called_once_with("work", "chatgpt")


def test_cmd_add_invalid_auth_type(tmp_path: Path) -> None:
    with patch("switcher.cli.print_error") as mock_err:
        cmd_add(argparse.Namespace(label="work", type="invalid"), "gemini")
    mock_err.assert_called_once()


def test_cmd_add_gemini_oauth_no_creds_user_declines(tmp_path: Path) -> None:
    profile = _make_profile(tmp_path, "work", "oauth")
    mgr = _make_manager([profile])
    mgr.add_profile.return_value = profile

    with (
        patch("switcher.cli.GeminiProfileManager", return_value=mgr),
        patch("switcher.cli._profile_has_oauth_creds", return_value=False),
        patch("switcher.cli.confirm", return_value=False),
        patch("switcher.cli.print_success"),
        patch("switcher.cli.print_warning"),
        patch("switcher.cli.print_info"),
    ):
        cmd_add(argparse.Namespace(label="work", type="oauth"), "gemini")
    # Should not crash, prints info about running later


def test_cmd_add_gemini_oauth_already_has_creds(tmp_path: Path) -> None:
    creds = {"token": {"refreshToken": "rt"}}
    profile = _make_profile(tmp_path, "work", "oauth", oauth_creds=creds)
    mgr = _make_manager([profile])
    mgr.add_profile.return_value = profile

    with (
        patch("switcher.cli.GeminiProfileManager", return_value=mgr),
        patch("switcher.cli.print_success"),
        patch("switcher.cli.print_info") as mock_info,
    ):
        cmd_add(argparse.Namespace(label="work", type="oauth"), "gemini")
    # Should report that existing creds were imported
    messages = " ".join(str(c) for c in mock_info.call_args_list)
    assert "Imported" in messages or "existing" in messages.lower()


# ---------------------------------------------------------------------------
# cmd_add — label prompt via input (EOFError branch)
# ---------------------------------------------------------------------------


def test_cmd_add_label_prompt_eof_exits(tmp_path: Path) -> None:
    """If user hits EOF when prompted for label, cmd_add returns silently."""
    with (
        patch("builtins.input", side_effect=EOFError),
        patch("switcher.cli.print_error"),
    ):
        cmd_add(argparse.Namespace(label=None, type="apikey"), "gemini")
    # No exception raised


def test_cmd_add_empty_label_prints_error(tmp_path: Path) -> None:
    with (
        patch("builtins.input", return_value=""),
        patch("switcher.cli.print_error") as mock_err,
    ):
        cmd_add(argparse.Namespace(label=None, type="apikey"), "gemini")
    mock_err.assert_called()


# ---------------------------------------------------------------------------
# _run_gemini_oauth_enrollment
# ---------------------------------------------------------------------------


def test_run_gemini_oauth_enrollment_gemini_not_found(tmp_path: Path) -> None:
    from switcher.cli import _run_gemini_oauth_enrollment

    profile = _make_profile(tmp_path, "work", "oauth")

    with (
        patch("switcher.utils.get_gemini_dir", return_value=tmp_path),
        patch("switcher.utils.atomic_symlink"),
        patch("switcher.auth.keyring_backend.keyring_delete"),
        patch("switcher.auth.gemini_auth.clear_gemini_cache"),
        patch("switcher.cli.print_info"),
        patch("subprocess.run", side_effect=FileNotFoundError),
        patch("switcher.cli.print_error") as mock_err,
    ):
        result = _run_gemini_oauth_enrollment(profile)
    assert result is False
    mock_err.assert_called()


def test_run_gemini_oauth_enrollment_no_creds_captured(tmp_path: Path) -> None:
    from unittest.mock import MagicMock

    from switcher.cli import _run_gemini_oauth_enrollment

    profile = _make_profile(tmp_path, "work", "oauth")
    mock_result = MagicMock()
    mock_result.returncode = 0

    with (
        patch("switcher.utils.get_gemini_dir", return_value=tmp_path),
        patch("switcher.utils.atomic_symlink"),
        patch("switcher.auth.keyring_backend.keyring_delete"),
        patch("switcher.auth.gemini_auth.clear_gemini_cache"),
        patch("switcher.cli.print_info"),
        patch("switcher.cli.print_warning"),
        patch("subprocess.run", return_value=mock_result),
        patch("switcher.cli._profile_has_oauth_creds", return_value=False),
        patch("switcher.cli._recover_profile_oauth_from_keyring", return_value=False),
    ):
        result = _run_gemini_oauth_enrollment(profile)
    assert result is False


def test_run_gemini_oauth_enrollment_success(tmp_path: Path) -> None:
    from unittest.mock import MagicMock

    from switcher.cli import _run_gemini_oauth_enrollment

    creds = {"token": {"refreshToken": "rt"}}
    profile = _make_profile(tmp_path, "work", "oauth", oauth_creds=creds)
    mock_result = MagicMock()
    mock_result.returncode = 0

    with (
        patch("switcher.utils.get_gemini_dir", return_value=tmp_path),
        patch("switcher.utils.atomic_symlink"),
        patch("switcher.auth.keyring_backend.keyring_delete"),
        patch("switcher.auth.gemini_auth.clear_gemini_cache"),
        patch("switcher.cli.print_info"),
        patch("switcher.cli.print_success") as mock_ok,
        patch("subprocess.run", return_value=mock_result),
    ):
        result = _run_gemini_oauth_enrollment(profile)
    assert result is True
    mock_ok.assert_called()


# ---------------------------------------------------------------------------
# cmd_config — error branches
# ---------------------------------------------------------------------------


def test_cmd_config_get_raises_switcher_error(capsys: pytest.CaptureFixture) -> None:
    from switcher.errors import SwitcherError

    with (
        patch("switcher.cli.get_config_value", side_effect=SwitcherError("bad key")),
        patch("switcher.cli.print_error") as mock_err,
    ):
        cmd_config(argparse.Namespace(key="get", value="bad.key", extra=[]))
    mock_err.assert_called_once()


def test_cmd_config_set_raises_switcher_error() -> None:
    from switcher.errors import SwitcherError

    with (
        patch("switcher.cli.set_config_value", side_effect=SwitcherError("bad")),
        patch("switcher.cli.print_error") as mock_err,
    ):
        cmd_config(argparse.Namespace(key="set", value="bad.key", extra=["val"]))
    mock_err.assert_called_once()


def test_cmd_config_legacy_get_raises_switcher_error() -> None:
    from switcher.errors import SwitcherError

    with (
        patch("switcher.cli.get_config_value", side_effect=SwitcherError("bad")),
        patch("switcher.cli.print_error") as mock_err,
    ):
        cmd_config(argparse.Namespace(key="bad.key", value=None, extra=[]))
    mock_err.assert_called_once()


def test_cmd_config_legacy_set_raises_switcher_error() -> None:
    from switcher.errors import SwitcherError

    with (
        patch("switcher.cli.set_config_value", side_effect=SwitcherError("bad")),
        patch("switcher.cli.print_error") as mock_err,
    ):
        cmd_config(argparse.Namespace(key="bad.key", value="v", extra=[]))
    mock_err.assert_called_once()


def test_cmd_config_legacy_extra_args_prints_error() -> None:
    with patch("switcher.cli.print_error") as mock_err:
        cmd_config(argparse.Namespace(key="bad.key", value="v", extra=["extra"]))
    mock_err.assert_called_once()


# ---------------------------------------------------------------------------
# cmd_switch — chatgpt prints restart message
# ---------------------------------------------------------------------------


def test_cmd_switch_codex_chatgpt_prints_restart(tmp_path: Path) -> None:
    profile = _make_profile(tmp_path, "work", "chatgpt")
    mgr = _make_manager([profile], active="work")

    with (
        patch("switcher.cli.CodexProfileManager", return_value=mgr),
        patch("switcher.cli.print_success"),
        patch("switcher.cli.print_info") as mock_info,
    ):
        cmd_switch(argparse.Namespace(target="work"), "codex")
    messages = " ".join(str(c) for c in mock_info.call_args_list)
    assert "Restart" in messages or "restart" in messages.lower()


# ---------------------------------------------------------------------------
# main() — KeyboardInterrupt
# ---------------------------------------------------------------------------


def test_main_catches_keyboard_interrupt() -> None:
    from switcher.cli import main

    with (
        patch("switcher.cli.ensure_dirs"),
        patch(
            "switcher.cli.load_config",
            return_value={"general": {"log_level": "info"}},
        ),
        patch("switcher.cli.setup_logging"),
        patch("switcher.cli._dispatch", side_effect=KeyboardInterrupt),
        patch("sys.argv", ["switcher", "version"]),
    ):
        try:
            main()
        except SystemExit as exc:
            assert exc.code == 130


# ---------------------------------------------------------------------------
# _quota_bar
# ---------------------------------------------------------------------------


def test_quota_bar_full() -> None:
    from switcher.cli import _quota_bar

    assert _quota_bar(100.0) == "██████████"


def test_quota_bar_empty() -> None:
    from switcher.cli import _quota_bar

    assert _quota_bar(0.0) == "░░░░░░░░░░"


def test_quota_bar_half() -> None:
    from switcher.cli import _quota_bar

    bar = _quota_bar(50.0)
    assert "█" in bar and "░" in bar
    assert len(bar) == 10


def test_quota_bar_clamps_above_100() -> None:
    from switcher.cli import _quota_bar

    assert _quota_bar(150.0) == "██████████"


def test_quota_bar_clamps_below_0() -> None:
    from switcher.cli import _quota_bar

    assert _quota_bar(-10.0) == "░░░░░░░░░░"


# ---------------------------------------------------------------------------
# _format_reset_date
# ---------------------------------------------------------------------------


def test_format_reset_date_valid_iso() -> None:
    from switcher.cli import _format_reset_date

    result = _format_reset_date("2025-04-01T00:00:00Z")
    assert "Apr" in result
    assert "2025" in result


def test_format_reset_date_invalid_returns_original() -> None:
    from switcher.cli import _format_reset_date

    assert _format_reset_date("not-a-date") == "not-a-date"


# ---------------------------------------------------------------------------
# cmd_health — quota display
# ---------------------------------------------------------------------------


def test_cmd_health_shows_quota_section(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    from switcher.health import ProfileQuotaInfo, QuotaEntry

    profile = _make_profile(tmp_path, "work", "oauth")
    mgr = _make_manager([profile])
    qi = ProfileQuotaInfo(
        email="alice@example.com",
        quotas=[
            QuotaEntry(
                model="gemini-2.5-pro",
                remaining_pct=73.0,
                reset_at="2025-04-01T00:00:00Z",
            ),
            QuotaEntry(model="gemini-2.0-flash", remaining_pct=15.0, reset_at=None),
        ],
        error=None,
    )

    with (
        patch("switcher.cli.GeminiProfileManager", return_value=mgr),
        patch(
            "switcher.health.check_all_profiles",
            return_value=[(profile, "valid", "OK", qi)],
        ),
        patch("switcher.cli.print_info"),
    ):
        cmd_health(argparse.Namespace(), "gemini")

    out = capsys.readouterr().out
    assert "alice@example.com" in out
    assert "gemini-2.5-pro" in out
    assert "27" in out  # 100 - 73 = 27% used (pro model)
    assert "85" in out  # 100 - 15 = 85% used (flash model)
    assert "⚠️" in out  # low-remaining quota warning


def test_cmd_health_quota_error_displayed(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    from switcher.health import ProfileQuotaInfo

    profile = _make_profile(tmp_path, "work", "oauth")
    mgr = _make_manager([profile])
    qi = ProfileQuotaInfo(email="bob@example.com", quotas=[], error="HTTP 500")

    with (
        patch("switcher.cli.GeminiProfileManager", return_value=mgr),
        patch(
            "switcher.health.check_all_profiles",
            return_value=[(profile, "valid", "OK", qi)],
        ),
        patch("switcher.cli.print_info"),
    ):
        cmd_health(argparse.Namespace(), "gemini")

    out = capsys.readouterr().out
    assert "HTTP 500" in out


def test_cmd_health_email_from_meta(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    profile = _make_profile(tmp_path, "work", "apikey")
    profile.meta["email"] = "stored@example.com"
    mgr = _make_manager([profile])

    with (
        patch("switcher.cli.GeminiProfileManager", return_value=mgr),
        patch(
            "switcher.health.check_all_profiles",
            return_value=[(profile, "valid", "OK", None)],
        ),
        patch("switcher.cli.print_info"),
    ):
        cmd_health(argparse.Namespace(), "gemini")

    out = capsys.readouterr().out
    assert "stored@example.com" in out
