"""Tests for switcher.ui_menu: run_menu, _handle_choice, _non_interactive_help."""

from __future__ import annotations

import argparse
import sys
from unittest.mock import patch

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parser() -> argparse.ArgumentParser:
    return argparse.ArgumentParser(prog="switcher")


# ---------------------------------------------------------------------------
# run_menu — non-interactive (non-TTY) branch
# ---------------------------------------------------------------------------


class TestRunMenuNonInteractive:
    def test_non_tty_prints_command_reference(self, capsys) -> None:
        from switcher.ui_menu import run_menu

        with patch.object(sys.stdin, "isatty", return_value=False):
            run_menu("gemini", _parser())

        out = capsys.readouterr().out
        assert "switcher gemini" in out
        assert "list" in out

    def test_non_tty_codex_shows_codex_commands(
        self, capsys
    ) -> None:
        from switcher.ui_menu import run_menu

        with patch.object(sys.stdin, "isatty", return_value=False):
            run_menu("codex", _parser())

        out = capsys.readouterr().out
        assert "switcher codex" in out

    def test_non_tty_does_not_prompt(self, capsys) -> None:
        from switcher.ui_menu import run_menu

        with (
            patch.object(sys.stdin, "isatty", return_value=False),
            patch("builtins.input") as mock_input,
        ):
            run_menu("gemini", _parser())
            mock_input.assert_not_called()


# ---------------------------------------------------------------------------
# run_menu — interactive (TTY) branch
# ---------------------------------------------------------------------------


class TestRunMenuInteractive:
    def test_keyboard_interrupt_exits_gracefully(
        self, capsys
    ) -> None:
        from switcher.ui_menu import run_menu

        with (
            patch.object(sys.stdin, "isatty", return_value=True),
            patch("switcher.state.get_active_profile", return_value="work"),
            patch("builtins.input", side_effect=KeyboardInterrupt),
        ):
            run_menu("gemini", _parser())  # Must not raise

    def test_eof_exits_gracefully(self, capsys) -> None:
        from switcher.ui_menu import run_menu

        with (
            patch.object(sys.stdin, "isatty", return_value=True),
            patch("switcher.state.get_active_profile", return_value=None),
            patch("builtins.input", side_effect=EOFError),
        ):
            run_menu("gemini", _parser())  # Must not raise

    def test_quit_choice_exits_loop(self, capsys) -> None:
        from switcher.ui_menu import run_menu

        with (
            patch.object(sys.stdin, "isatty", return_value=True),
            patch("switcher.state.get_active_profile", return_value=None),
            patch("builtins.input", return_value="q"),
        ):
            run_menu("gemini", _parser())
        # No infinite loop; test completes


# ---------------------------------------------------------------------------
# _handle_choice
# ---------------------------------------------------------------------------


class TestHandleChoice:
    def _call(self, choice: str, cli_name: str = "gemini") -> bool:
        from switcher.ui_menu import _handle_choice

        return _handle_choice(choice, cli_name, _parser())

    def test_quit_returns_false(self) -> None:
        assert self._call("q") is False

    def test_quit_alias_exit_returns_false(self) -> None:
        assert self._call("exit") is False

    def test_quit_alias_quit_returns_false(self) -> None:
        assert self._call("quit") is False

    def test_invalid_choice_string_returns_true(
        self, capsys
    ) -> None:
        result = self._call("xyz")
        assert result is True  # should not raise

    def test_out_of_range_number_returns_true(self, capsys) -> None:
        result = self._call("99")
        assert result is True

    def test_zero_index_returns_true(self, capsys) -> None:
        result = self._call("0")
        assert result is True

    def test_list_action_calls_cmd_list(self, capsys) -> None:
        from switcher.ui_menu import _handle_choice

        with patch("switcher.cli.cmd_list") as mock_list:
            # "list" is choice 1 for gemini
            result = _handle_choice("1", "gemini", _parser())

        assert result is True
        mock_list.assert_called_once()

    def test_next_action_calls_cmd_next(self) -> None:
        from switcher.ui_menu import _handle_choice

        with patch("switcher.cli.cmd_next") as mock_next:
            # "next" is choice 3 for gemini
            result = _handle_choice("3", "gemini", _parser())

        assert result is True
        mock_next.assert_called_once()

    def test_health_action_calls_cmd_health(self) -> None:
        from switcher.ui_menu import _handle_choice

        with patch("switcher.cli.cmd_health") as mock_health:
            # "health" is choice 5 for gemini
            result = _handle_choice("5", "gemini", _parser())

        assert result is True
        mock_health.assert_called_once()

    def test_exception_in_handler_returns_true(
        self, capsys
    ) -> None:
        from switcher.ui_menu import _handle_choice

        with patch("switcher.cli.cmd_list", side_effect=RuntimeError("boom")):
            result = _handle_choice("1", "gemini", _parser())

        assert result is True  # error is caught, loop continues

    def test_switch_action_prompts_for_target(self) -> None:
        from switcher.ui_menu import _handle_choice

        with (
            patch("builtins.input", return_value="work"),
            patch("switcher.cli.cmd_switch") as mock_switch,
        ):
            # "switch" is choice 2 for gemini
            result = _handle_choice("2", "gemini", _parser())

        assert result is True
        mock_switch.assert_called_once()

    def test_switch_with_empty_target_skips(self) -> None:
        from switcher.ui_menu import _handle_choice

        with (
            patch("builtins.input", return_value=""),
            patch("switcher.cli.cmd_switch") as mock_switch,
        ):
            result = _handle_choice("2", "gemini", _parser())

        assert result is True
        mock_switch.assert_not_called()


# ---------------------------------------------------------------------------
# _toggle_auto_rotate
# ---------------------------------------------------------------------------


class TestToggleAutoRotate:
    def test_toggle_flips_enabled_true_to_false(self) -> None:
        from switcher.ui_menu import _toggle_auto_rotate

        with (
            patch("switcher.config.get_config_value", return_value=True),
            patch("switcher.config.set_config_value") as mock_set,
            patch("switcher.ui.print_success"),
        ):
            _toggle_auto_rotate()

        mock_set.assert_called_once_with("auto_rotate.enabled", False)

    def test_toggle_flips_enabled_false_to_true(self) -> None:
        from switcher.ui_menu import _toggle_auto_rotate

        with (
            patch("switcher.config.get_config_value", return_value=False),
            patch("switcher.config.set_config_value") as mock_set,
            patch("switcher.ui.print_success"),
        ):
            _toggle_auto_rotate()

        mock_set.assert_called_once_with("auto_rotate.enabled", True)
