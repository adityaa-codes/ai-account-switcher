"""Tests for cmd_change, cmd_quota, pool dispatch, and new CLI subcommands."""

from __future__ import annotations

import argparse
from unittest.mock import MagicMock, patch

from switcher.cli import (
    _dispatch,
    build_parser,
    cmd_change,
    cmd_quota,
)

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
