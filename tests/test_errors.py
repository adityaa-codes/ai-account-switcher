"""Tests for the custom exception hierarchy."""

from __future__ import annotations

import pytest

from switcher.errors import (
    AuthError,
    ConfigError,
    HookError,
    KeyringError,
    ProfileCorruptError,
    ProfileNotFoundError,
    SwitcherError,
    TokenExpiredError,
)


def test_all_errors_inherit_switcher_error() -> None:
    for cls in (
        ProfileNotFoundError,
        ProfileCorruptError,
        AuthError,
        KeyringError,
        TokenExpiredError,
        ConfigError,
        HookError,
    ):
        assert issubclass(cls, SwitcherError), (
            f"{cls.__name__} must subclass SwitcherError"
        )


def test_keyring_error_is_auth_error() -> None:
    assert issubclass(KeyringError, AuthError)


def test_token_expired_error_is_auth_error() -> None:
    assert issubclass(TokenExpiredError, AuthError)


def test_errors_are_catchable_as_base() -> None:
    for cls in (
        ProfileNotFoundError,
        ProfileCorruptError,
        AuthError,
        KeyringError,
        TokenExpiredError,
        ConfigError,
        HookError,
    ):
        try:
            raise cls("test message")
        except SwitcherError as exc:
            assert str(exc) == "test message"
        else:
            pytest.fail(f"{cls.__name__} not caught as SwitcherError")
