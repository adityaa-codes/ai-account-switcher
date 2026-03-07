"""Tests for switcher.auth.keyring_backend.

Covers detect_keyring_mode (all branches), keyring_read, keyring_write,
and keyring_delete, including the PasswordDeleteError silent-ignore path.
"""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest

import switcher.auth.keyring_backend as kb
from switcher.errors import KeyringError

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_keyring_mock(backend_name: str = "SecretServiceKeyring") -> MagicMock:
    """Build a minimal keyring module mock with a named backend."""
    mock_mod = MagicMock()
    backend_instance = MagicMock()
    type(backend_instance).__name__ = backend_name
    mock_mod.get_keyring.return_value = backend_instance
    return mock_mod


# ---------------------------------------------------------------------------
# detect_keyring_mode — forced modes
# ---------------------------------------------------------------------------


def test_detect_force_keyring_returns_keyring() -> None:
    assert kb.detect_keyring_mode(force_mode="keyring") == "keyring"


def test_detect_force_file_returns_file() -> None:
    assert kb.detect_keyring_mode(force_mode="file") == "file"


# ---------------------------------------------------------------------------
# detect_keyring_mode — cache
# ---------------------------------------------------------------------------


def test_detect_uses_cache_when_available_true(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(kb, "_KEYRING_AVAILABLE", True)
    assert kb.detect_keyring_mode() == "keyring"


def test_detect_uses_cache_when_available_false(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(kb, "_KEYRING_AVAILABLE", False)
    assert kb.detect_keyring_mode() == "file"


# ---------------------------------------------------------------------------
# detect_keyring_mode — no graphical session
# ---------------------------------------------------------------------------


def test_detect_no_display_no_wayland_returns_file(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    monkeypatch.setattr(kb, "_KEYRING_AVAILABLE", None)

    result = kb.detect_keyring_mode()

    assert result == "file"
    assert kb._KEYRING_AVAILABLE is False


# ---------------------------------------------------------------------------
# detect_keyring_mode — graphical session + backend probe
# ---------------------------------------------------------------------------


def _patch_keyring(
    mock_mod: MagicMock,
    fail_keyring_class: type,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Set up sys.modules and DISPLAY for a keyring probe test."""
    monkeypatch.setenv("DISPLAY", ":0")
    monkeypatch.setattr(kb, "_KEYRING_AVAILABLE", None)

    fail_mod = MagicMock()
    fail_mod.Keyring = fail_keyring_class

    with patch.dict(
        sys.modules,
        {
            "keyring": mock_mod,
            "keyring.backends": MagicMock(),
            "keyring.backends.fail": fail_mod,
        },
    ):
        yield  # type: ignore[misc]


def test_detect_good_backend_returns_keyring(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DISPLAY", ":0")
    monkeypatch.setattr(kb, "_KEYRING_AVAILABLE", None)

    class FailKeyringClass:
        pass

    mock_mod = _make_keyring_mock("SecretServiceKeyring")
    fail_mod = MagicMock()
    fail_mod.Keyring = FailKeyringClass

    with patch.dict(
        sys.modules,
        {
            "keyring": mock_mod,
            "keyring.backends": MagicMock(),
            "keyring.backends.fail": fail_mod,
        },
    ):
        result = kb.detect_keyring_mode()

    assert result == "keyring"
    assert kb._KEYRING_AVAILABLE is True


def test_detect_fail_keyring_instance_returns_file(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DISPLAY", ":0")
    monkeypatch.setattr(kb, "_KEYRING_AVAILABLE", None)

    class FailKeyringClass:
        pass

    fail_instance = FailKeyringClass()
    type(fail_instance).__name__ = "Keyring"

    mock_mod = MagicMock()
    mock_mod.get_keyring.return_value = fail_instance

    fail_mod = MagicMock()
    fail_mod.Keyring = FailKeyringClass

    with patch.dict(
        sys.modules,
        {
            "keyring": mock_mod,
            "keyring.backends": MagicMock(),
            "keyring.backends.fail": fail_mod,
        },
    ):
        result = kb.detect_keyring_mode()

    assert result == "file"
    assert kb._KEYRING_AVAILABLE is False


def test_detect_plaintext_backend_returns_file(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DISPLAY", ":0")
    monkeypatch.setattr(kb, "_KEYRING_AVAILABLE", None)

    class FailKeyringClass:
        pass

    mock_mod = _make_keyring_mock("PlaintextKeyring")
    fail_mod = MagicMock()
    fail_mod.Keyring = FailKeyringClass

    with patch.dict(
        sys.modules,
        {
            "keyring": mock_mod,
            "keyring.backends": MagicMock(),
            "keyring.backends.fail": fail_mod,
        },
    ):
        result = kb.detect_keyring_mode()

    assert result == "file"
    assert kb._KEYRING_AVAILABLE is False


def test_detect_keyring_import_exception_returns_file(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DISPLAY", ":0")
    monkeypatch.setattr(kb, "_KEYRING_AVAILABLE", None)

    # Removing keyring from sys.modules and replacing with None forces ImportError
    # on `import keyring` inside detect_keyring_mode.
    with patch.dict(sys.modules, {"keyring": None}):  # type: ignore[dict-item]
        result = kb.detect_keyring_mode()

    assert result == "file"
    assert kb._KEYRING_AVAILABLE is False


def test_detect_wayland_display_triggers_probe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """WAYLAND_DISPLAY (without DISPLAY) should still trigger the keyring probe."""
    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.setenv("WAYLAND_DISPLAY", ":0")
    monkeypatch.setattr(kb, "_KEYRING_AVAILABLE", None)

    class FailKeyringClass:
        pass

    mock_mod = _make_keyring_mock("SecretServiceKeyring")
    fail_mod = MagicMock()
    fail_mod.Keyring = FailKeyringClass

    with patch.dict(
        sys.modules,
        {
            "keyring": mock_mod,
            "keyring.backends": MagicMock(),
            "keyring.backends.fail": fail_mod,
        },
    ):
        result = kb.detect_keyring_mode()

    assert result == "keyring"


# ---------------------------------------------------------------------------
# keyring_read
# ---------------------------------------------------------------------------


def test_keyring_read_returns_value() -> None:
    mock_mod = MagicMock()
    mock_mod.get_password.return_value = "super-secret"

    with patch.dict(sys.modules, {"keyring": mock_mod}):
        result = kb.keyring_read("my-service", "my-key")

    assert result == "super-secret"
    mock_mod.get_password.assert_called_once_with("my-service", "my-key")


def test_keyring_read_returns_none_when_missing() -> None:
    mock_mod = MagicMock()
    mock_mod.get_password.return_value = None

    with patch.dict(sys.modules, {"keyring": mock_mod}):
        result = kb.keyring_read("svc", "k")

    assert result is None


def test_keyring_read_raises_keyring_error_on_exception() -> None:
    mock_mod = MagicMock()
    mock_mod.get_password.side_effect = RuntimeError("keyring daemon crashed")

    with (
        patch.dict(sys.modules, {"keyring": mock_mod}),
        pytest.raises(KeyringError, match=r"Failed to read keyring.*svc/k"),
    ):
        kb.keyring_read("svc", "k")


# ---------------------------------------------------------------------------
# keyring_write
# ---------------------------------------------------------------------------


def test_keyring_write_calls_set_password() -> None:
    mock_mod = MagicMock()

    with patch.dict(sys.modules, {"keyring": mock_mod}):
        kb.keyring_write("svc", "k", "v")

    mock_mod.set_password.assert_called_once_with("svc", "k", "v")


def test_keyring_write_raises_keyring_error_on_exception() -> None:
    mock_mod = MagicMock()
    mock_mod.set_password.side_effect = OSError("permission denied")

    with (
        patch.dict(sys.modules, {"keyring": mock_mod}),
        pytest.raises(KeyringError, match=r"Failed to write keyring.*svc/k"),
    ):
        kb.keyring_write("svc", "k", "v")


# ---------------------------------------------------------------------------
# keyring_delete
# ---------------------------------------------------------------------------


def test_keyring_delete_calls_delete_password() -> None:
    mock_mod = MagicMock()

    with patch.dict(sys.modules, {"keyring": mock_mod}):
        kb.keyring_delete("svc", "k")

    mock_mod.delete_password.assert_called_once_with("svc", "k")


def test_keyring_delete_silently_ignores_password_delete_error() -> None:
    """Deleting a non-existent entry should not raise."""

    class PasswordDeleteError(Exception):
        pass

    mock_mod = MagicMock()
    mock_mod.errors = MagicMock()
    mock_mod.errors.PasswordDeleteError = PasswordDeleteError
    mock_mod.delete_password.side_effect = PasswordDeleteError("entry not found")

    with patch.dict(sys.modules, {"keyring": mock_mod}):
        # Must not raise
        kb.keyring_delete("svc", "k")


def test_keyring_delete_raises_keyring_error_on_other_exception() -> None:
    class PasswordDeleteError(Exception):
        pass

    mock_mod = MagicMock()
    mock_mod.errors = MagicMock()
    mock_mod.errors.PasswordDeleteError = PasswordDeleteError
    mock_mod.delete_password.side_effect = RuntimeError("unexpected daemon error")

    with (
        patch.dict(sys.modules, {"keyring": mock_mod}),
        pytest.raises(KeyringError, match=r"Failed to delete keyring.*svc/k"),
    ):
        kb.keyring_delete("svc", "k")
