"""Tests for cmd_change, cmd_quota, pool dispatch, and new CLI subcommands."""

from __future__ import annotations

import argparse
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

from switcher.cli import (
    _dispatch,
    build_parser,
    cmd_change,
    cmd_quota,
)

if TYPE_CHECKING:
    from pathlib import Path

# ---------------------------------------------------------------------------
# cmd_change routing
# ---------------------------------------------------------------------------


class TestCmdChange:
    def _args(self, target: str | None) -> argparse.Namespace:
        return argparse.Namespace(command="gemini", action="change", target=target)

    def test_no_target_delegates_to_cmd_next(self) -> None:
        args = self._args(None)
        with patch("switcher.cli.cmd_next") as mock_next:
            cmd_change(args, "gemini")
        mock_next.assert_called_once_with(args, "gemini")

    def test_next_keyword_delegates_to_cmd_next(self) -> None:
        args = self._args("next")
        with patch("switcher.cli.cmd_next") as mock_next:
            cmd_change(args, "gemini")
        mock_next.assert_called_once_with(args, "gemini")

    def test_next_keyword_case_insensitive(self) -> None:
        args = self._args("NEXT")
        with patch("switcher.cli.cmd_next") as mock_next:
            cmd_change(args, "gemini")
        mock_next.assert_called_once()

    def test_label_target_delegates_to_cmd_switch(self) -> None:
        args = self._args("work")
        with patch("switcher.cli.cmd_switch") as mock_switch:
            cmd_change(args, "gemini")
        mock_switch.assert_called_once_with(args, "gemini")

    def test_numeric_target_delegates_to_cmd_switch(self) -> None:
        args = self._args("2")
        with patch("switcher.cli.cmd_switch") as mock_switch:
            cmd_change(args, "gemini")
        mock_switch.assert_called_once_with(args, "gemini")

    def test_dispatch_change_action_routes_correctly(self) -> None:
        parser = build_parser()
        mock_change = MagicMock()
        with patch.dict("switcher.cli._CLI_ACTIONS", {"change": mock_change}):
            _dispatch(
                parser,
                argparse.Namespace(command="gemini", action="change", target=None),
            )
        mock_change.assert_called_once()


# ---------------------------------------------------------------------------
# cmd_quota
# ---------------------------------------------------------------------------


class TestCmdQuota:
    def test_codex_prints_warning_and_returns(self, capsys) -> None:
        args = argparse.Namespace(command="codex", action="quota")
        cmd_quota(args, "codex")
        out = capsys.readouterr().out
        assert "only available for Gemini" in out

    def test_no_oauth_profiles_prints_warning(self, capsys) -> None:
        args = argparse.Namespace(command="gemini", action="quota")
        mgr_mock = MagicMock()
        mgr_mock.list_profiles.return_value = []  # no profiles
        with patch("switcher.cli._get_manager", return_value=mgr_mock):
            cmd_quota(args, "gemini")
        out = capsys.readouterr().out
        assert "No Gemini OAuth profiles" in out

    def test_api_key_profiles_are_skipped(self, capsys) -> None:
        args = argparse.Namespace(command="gemini", action="quota")
        profile = MagicMock()
        profile.auth_type = "api_key"
        profile.label = "work-apikey"
        mgr_mock = MagicMock()
        mgr_mock.list_profiles.return_value = [profile]
        with patch("switcher.cli._get_manager", return_value=mgr_mock):
            cmd_quota(args, "gemini")
        out = capsys.readouterr().out
        assert "No Gemini OAuth profiles" in out

    def test_oauth_profile_with_quota_data_is_displayed(
        self, capsys
    ) -> None:
        args = argparse.Namespace(command="gemini", action="quota")

        profile = MagicMock()
        profile.auth_type = "oauth"
        profile.label = "personal"

        quota_item = MagicMock()
        quota_item.model = "gemini-2.0-flash"
        quota_item.remaining_pct = 80.0
        quota_item.reset_at = None

        qi = MagicMock()
        qi.email = "user@example.com"
        qi.error = None
        qi.quotas = [quota_item]

        mgr_mock = MagicMock()
        mgr_mock.list_profiles.return_value = [profile]

        with (
            patch("switcher.cli._get_manager", return_value=mgr_mock),
            patch("switcher.cli.fetch_quota_info", return_value=qi, create=True),
            patch("switcher.state.get_active_profile", return_value=None),
            patch("switcher.health.fetch_quota_info", return_value=qi),
        ):
            cmd_quota(args, "gemini")

        out = capsys.readouterr().out
        assert "personal" in out

    def test_oauth_profile_with_error_shows_warning(
        self, capsys
    ) -> None:
        args = argparse.Namespace(command="gemini", action="quota")

        profile = MagicMock()
        profile.auth_type = "oauth"
        profile.label = "work"

        qi = MagicMock()
        qi.email = None
        qi.error = "Token expired"
        qi.quotas = []

        mgr_mock = MagicMock()
        mgr_mock.list_profiles.return_value = [profile]

        with (
            patch("switcher.cli._get_manager", return_value=mgr_mock),
            patch("switcher.health.fetch_quota_info", return_value=qi),
            patch("switcher.state.get_active_profile", return_value=None),
        ):
            cmd_quota(args, "gemini")

        out = capsys.readouterr().out
        assert "Token expired" in out

    def test_dispatch_quota_action_routes_correctly(self) -> None:
        parser = build_parser()
        mock_quota = MagicMock()
        with patch.dict("switcher.cli._CLI_ACTIONS", {"quota": mock_quota}):
            _dispatch(
                parser,
                argparse.Namespace(command="gemini", action="quota"),
            )
        mock_quota.assert_called_once()


# ---------------------------------------------------------------------------
# pool dispatch (alias routing)
# ---------------------------------------------------------------------------


class TestPoolDispatch:
    def test_pool_no_subaction_calls_cmd_list(self) -> None:
        parser = build_parser()
        with patch("switcher.cli.cmd_list") as mock_list:
            _dispatch(
                parser,
                argparse.Namespace(command="gemini", action="pool", pool_action=None),
            )
        mock_list.assert_called_once()

    def test_pool_add_calls_cmd_add(self) -> None:
        parser = build_parser()
        mock_add = MagicMock()
        with patch.dict("switcher.cli._POOL_ACTIONS", {"add": mock_add}):
            _dispatch(
                parser,
                argparse.Namespace(
                    command="gemini",
                    action="pool",
                    pool_action="add",
                    label=None,
                    type=None,
                ),
            )
        mock_add.assert_called_once()

    def test_pool_remove_calls_cmd_remove(self) -> None:
        parser = build_parser()
        mock_remove = MagicMock()
        with patch.dict("switcher.cli._POOL_ACTIONS", {"remove": mock_remove}):
            _dispatch(
                parser,
                argparse.Namespace(
                    command="gemini",
                    action="pool",
                    pool_action="remove",
                    label="work",
                ),
            )
        mock_remove.assert_called_once()

    def test_pool_import_calls_cmd_import(self) -> None:
        parser = build_parser()
        mock_import = MagicMock()
        with patch.dict("switcher.cli._POOL_ACTIONS", {"import": mock_import}):
            _dispatch(
                parser,
                argparse.Namespace(
                    command="gemini",
                    action="pool",
                    pool_action="import",
                    path="/tmp/creds.json",
                    label=None,
                ),
            )
        mock_import.assert_called_once()

    def test_pool_unknown_subaction_calls_cmd_list(self) -> None:
        """Unknown pool sub-action should fall back to listing."""
        parser = build_parser()
        with patch("switcher.cli.cmd_list") as mock_list:
            _dispatch(
                parser,
                argparse.Namespace(
                    command="gemini",
                    action="pool",
                    pool_action="unknown_action",
                ),
            )
        mock_list.assert_called_once()


# ---------------------------------------------------------------------------
# menu dispatch
# ---------------------------------------------------------------------------


class TestMenuDispatch:
    def test_dispatch_menu_action_routes_correctly(self) -> None:
        parser = build_parser()
        mock_menu = MagicMock()
        with patch.dict("switcher.cli._CLI_ACTIONS", {"menu": mock_menu}):
            _dispatch(
                parser,
                argparse.Namespace(command="gemini", action="menu"),
            )
        mock_menu.assert_called_once()


# ---------------------------------------------------------------------------
# Phase 3: pool health / export / status dispatch (D-1 through D-4)
# ---------------------------------------------------------------------------


class TestPoolExtendedDispatch:
    def test_pool_list_routes_to_cmd_list(self) -> None:
        """D-1: pool list should delegate to cmd_list."""
        parser = build_parser()
        mock_list = MagicMock()
        with patch.dict("switcher.cli._POOL_ACTIONS", {"list": mock_list}):
            _dispatch(
                parser,
                argparse.Namespace(command="gemini", action="pool", pool_action="list"),
            )
        mock_list.assert_called_once()

    def test_pool_health_routes_to_cmd_health(self) -> None:
        """D-2: pool health should delegate to cmd_health."""
        parser = build_parser()
        mock_health = MagicMock()
        with patch.dict("switcher.cli._POOL_ACTIONS", {"health": mock_health}):
            _dispatch(
                parser,
                argparse.Namespace(
                    command="gemini", action="pool", pool_action="health"
                ),
            )
        mock_health.assert_called_once()

    def test_pool_export_routes_to_cmd_export(self) -> None:
        """D-3: pool export should delegate to cmd_export."""
        parser = build_parser()
        mock_export = MagicMock()
        with patch.dict("switcher.cli._POOL_ACTIONS", {"export": mock_export}):
            _dispatch(
                parser,
                argparse.Namespace(
                    command="gemini",
                    action="pool",
                    pool_action="export",
                    target="work",
                    dest=None,
                ),
            )
        mock_export.assert_called_once()

    def test_pool_status_routes_to_cmd_pool_status(self) -> None:
        """D-4: pool status should delegate to cmd_pool_status."""
        parser = build_parser()
        mock_status = MagicMock()
        with patch.dict("switcher.cli._POOL_ACTIONS", {"status": mock_status}):
            _dispatch(
                parser,
                argparse.Namespace(
                    command="gemini", action="pool", pool_action="status"
                ),
            )
        mock_status.assert_called_once()

    def test_pool_status_output(self, tmp_path: Path, capsys: object) -> None:
        """D-4: cmd_pool_status prints one line per profile."""
        from switcher.cli import cmd_pool_status
        from switcher.profiles.base import Profile

        fake_profile = Profile(
            label="work",
            auth_type="oauth",
            path=tmp_path / "work",
            meta={"last_used": "2025-01-01"},
        )

        with (
            patch("switcher.cli._get_manager") as mock_mgr,
            patch("switcher.cli.get_active_profile", return_value="work"),
            patch("switcher.health.check_profile", return_value=("valid", "")),
        ):
            mock_mgr.return_value.list_profiles.return_value = [fake_profile]
            cmd_pool_status(
                argparse.Namespace(
                    command="gemini", action="pool", pool_action="status"
                ),
                "gemini",
            )

        captured = capsys.readouterr()  # type: ignore[attr-defined]
        assert "work" in captured.out
        assert "oauth" in captured.out


# ---------------------------------------------------------------------------
# Phase 5: alerts, version --check, quota display (I-1, I-3, I-4)
# ---------------------------------------------------------------------------


class TestAlertsCommand:
    def test_alerts_no_log_file(
        self, tmp_path: Path, capsys: object
    ) -> None:
        """I-3: alerts prints clean message when no errors.log exists."""
        from switcher.cli import cmd_alerts

        with patch("switcher.utils.get_config_dir", return_value=tmp_path):
            cmd_alerts(argparse.Namespace(lines=20))

        out = capsys.readouterr().out  # type: ignore[attr-defined]
        assert "clean" in out.lower() or "no error" in out.lower()

    def test_alerts_shows_last_n_lines(
        self, tmp_path: Path, capsys: object
    ) -> None:
        """I-3: alerts tails --lines N lines from errors.log."""
        from switcher.cli import cmd_alerts

        logs_dir = tmp_path / "logs"
        logs_dir.mkdir()
        errors_log = logs_dir / "errors.log"
        errors_log.write_text(
            "\n".join(f"2025-01-01 ERROR line-{i}" for i in range(30))
        )

        with patch("switcher.utils.get_config_dir", return_value=tmp_path):
            cmd_alerts(argparse.Namespace(lines=5))

        out = capsys.readouterr().out  # type: ignore[attr-defined]
        assert "line-29" in out
        assert "line-25" in out
        # Should NOT show early lines
        assert "line-0" not in out

    def test_alerts_dispatch(self) -> None:
        """I-3: 'alerts' command is dispatched by _dispatch."""
        parser = build_parser()
        with patch("switcher.cli.cmd_alerts") as mock_alerts:
            _dispatch(parser, argparse.Namespace(command="alerts", lines=20))
        mock_alerts.assert_called_once()


class TestDoctorCommand:
    def test_doctor_dispatch(self) -> None:
        """Doctor command is dispatched by _dispatch."""
        parser = build_parser()
        with patch("switcher.cli.cmd_doctor") as mock_doctor:
            _dispatch(parser, argparse.Namespace(command="doctor"))
        mock_doctor.assert_called_once()

    def test_doctor_no_issues(self, tmp_path: Path, capsys: object) -> None:
        """Doctor prints success when no auth conflicts are detected."""
        from switcher.cli import cmd_doctor

        gm = MagicMock()
        gm.list_profiles.return_value = []
        cm = MagicMock()
        cm.list_profiles.return_value = []

        with (
            patch("switcher.cli.GeminiProfileManager", return_value=gm),
            patch("switcher.cli.CodexProfileManager", return_value=cm),
            patch("switcher.cli.get_active_profile", return_value=None),
            patch("switcher.utils.get_config_dir", return_value=tmp_path),
        ):
            cmd_doctor(argparse.Namespace())

        out = capsys.readouterr().out  # type: ignore[attr-defined]
        assert "no auth conflicts" in out.lower()

    def test_doctor_detects_oauth_env_conflicts(
        self, tmp_path: Path, capsys: object
    ) -> None:
        """Doctor flags stale API-key exports for OAuth active profiles."""
        from switcher.cli import cmd_doctor

        env_file = tmp_path / "env.sh"
        env_file.write_text(
            '\n'.join(
                [
                    'export GEMINI_API_KEY="AIza-stale"',
                    'export GOOGLE_API_KEY="AIza-stale"',
                    'export OPENAI_API_KEY="sk-stale"',
                    "",
                ]
            ),
            encoding="utf-8",
        )

        gm_profile = MagicMock()
        gm_profile.label = "g-oauth"
        gm_profile.auth_type = "oauth"
        gm_profile.path = tmp_path / "profiles" / "gemini" / "g-oauth"
        gm_profile.path.mkdir(parents=True, exist_ok=True)
        (gm_profile.path / "oauth_creds.json").write_text("{}", encoding="utf-8")

        cm_profile = MagicMock()
        cm_profile.label = "c-oauth"
        cm_profile.auth_type = "chatgpt"
        cm_profile.path = tmp_path / "profiles" / "codex" / "c-oauth"
        cm_profile.path.mkdir(parents=True, exist_ok=True)
        (cm_profile.path / "auth.json").write_text("{}", encoding="utf-8")

        gm = MagicMock()
        gm.list_profiles.return_value = [gm_profile]
        cm = MagicMock()
        cm.list_profiles.return_value = [cm_profile]

        def active(cli: str) -> str | None:
            if cli == "gemini":
                return "g-oauth"
            if cli == "codex":
                return "c-oauth"
            return None

        with (
            patch("switcher.cli.GeminiProfileManager", return_value=gm),
            patch("switcher.cli.CodexProfileManager", return_value=cm),
            patch("switcher.cli.get_active_profile", side_effect=active),
            patch("switcher.utils.get_config_dir", return_value=tmp_path),
            patch("switcher.utils.get_gemini_dir", return_value=tmp_path / ".gemini"),
            patch("switcher.utils.get_codex_dir", return_value=tmp_path / ".codex"),
        ):
            cmd_doctor(argparse.Namespace())

        out = capsys.readouterr().out  # type: ignore[attr-defined]
        assert "issue" in out.lower()
        assert "gemini" in out.lower()
        assert "openai_api_key" in out.lower()


class TestVersionCheck:
    def test_version_no_check_prints_version(
        self, capsys: object
    ) -> None:
        """I-4: version without --check just prints version."""
        from switcher.cli import cmd_version

        cmd_version(argparse.Namespace(check=False))
        out = capsys.readouterr().out  # type: ignore[attr-defined]
        assert "ai-account-switcher" in out

    def test_version_check_up_to_date(self, capsys: object) -> None:
        """I-4: version --check prints 'Up to date' when versions match."""
        from switcher import __version__
        from switcher.cli import cmd_version

        mock_resp = MagicMock()
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_resp.read.return_value = (
            f'{{"info": {{"version": "{__version__}"}}}}'
        ).encode()

        with patch("urllib.request.urlopen", return_value=mock_resp):
            cmd_version(argparse.Namespace(check=True))

        out = capsys.readouterr().out  # type: ignore[attr-defined]
        assert "up to date" in out.lower()

    def test_version_check_update_available(self, capsys: object) -> None:
        """I-4: version --check prints update notice when newer version exists."""
        from switcher.cli import cmd_version

        mock_resp = MagicMock()
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_resp.read.return_value = b'{"info": {"version": "99.99.99"}}'

        with patch("urllib.request.urlopen", return_value=mock_resp):
            cmd_version(argparse.Namespace(check=True))

        out = capsys.readouterr().out  # type: ignore[attr-defined]
        assert "99.99.99" in out

    def test_version_check_network_error_silently_skipped(
        self, capsys: object
    ) -> None:
        """I-4: version --check silently skips on network error."""
        from switcher.cli import cmd_version

        with patch("urllib.request.urlopen", side_effect=OSError("no network")):
            cmd_version(argparse.Namespace(check=True))

        # Should not raise; output is just the version line
        out = capsys.readouterr().out  # type: ignore[attr-defined]
        assert "ai-account-switcher" in out
