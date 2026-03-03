"""Tests for terminal output rendering."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import patch

from switcher.ui import confirm, print_profile_list, print_table

if TYPE_CHECKING:
    from pytest import CaptureFixture


def test_print_table_no_rows_shows_placeholder(capsys: CaptureFixture[str]) -> None:
    print_table(["#", "Label", "Type"], [])
    captured = capsys.readouterr()
    assert "(no entries)" in captured.out


def test_print_table_renders_headers_and_rows(capsys: CaptureFixture[str]) -> None:
    print_table(["#", "Label"], [["01.", "work@example.com"]])
    captured = capsys.readouterr()
    assert "Label" in captured.out
    assert "work@example.com" in captured.out


def test_print_profile_list_marks_active_profile(
    capsys: CaptureFixture[str],
) -> None:
    profiles = [
        {"label": "personal", "auth_type": "oauth", "health_status": "valid"},
        {"label": "work", "auth_type": "apikey", "health_status": "unknown"},
    ]
    print_profile_list(profiles, active="personal", cli_name="gemini")
    captured = capsys.readouterr()
    assert "●" in captured.out  # active marker
    assert "○" in captured.out  # inactive marker


def test_print_profile_list_empty_shows_no_profiles(
    capsys: CaptureFixture[str],
) -> None:
    print_profile_list([], active=None, cli_name="gemini")
    captured = capsys.readouterr()
    assert "No profiles configured" in captured.out


def test_confirm_returns_true_on_yes() -> None:
    with patch("builtins.input", return_value="y"):
        assert confirm("Continue?") is True


def test_confirm_returns_true_on_yes_upper() -> None:
    with patch("builtins.input", return_value="YES"):
        assert confirm("Continue?") is True


def test_confirm_returns_false_on_no() -> None:
    with patch("builtins.input", return_value="n"):
        assert confirm("Continue?") is False


def test_confirm_returns_false_on_empty() -> None:
    with patch("builtins.input", return_value=""):
        assert confirm("Continue?") is False


def test_confirm_returns_false_on_eof() -> None:
    with patch("builtins.input", side_effect=EOFError):
        assert confirm("Continue?") is False


def test_print_profile_list_shows_auth_type_label(
    capsys: CaptureFixture[str],
) -> None:
    profiles = [{"label": "work", "auth_type": "apikey", "health_status": "valid"}]
    print_profile_list(profiles, active=None, cli_name="codex")
    captured = capsys.readouterr()
    assert "API Key" in captured.out
