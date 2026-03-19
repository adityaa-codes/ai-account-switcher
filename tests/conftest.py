"""Shared pytest fixtures for ai-account-switcher tests."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock

import pytest

if TYPE_CHECKING:
    from pathlib import Path

    from pytest import MonkeyPatch


@pytest.fixture()
def tmp_config_dir(tmp_path: Path, monkeypatch: MonkeyPatch) -> Path:
    """Redirect all config/state I/O to a temp directory.

    Sets XDG_CONFIG_HOME and HOME so get_config_dir(), get_gemini_dir(),
    and get_codex_dir() never touch the real user home.

    Returns:
        The temp path used as the fake home root.
    """
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / ".config"))
    monkeypatch.setenv("HOME", str(tmp_path))
    # Bust the module-level cache in keyring_backend if present
    import switcher.auth.keyring_backend as kb

    monkeypatch.setattr(kb, "_KEYRING_AVAILABLE", None)
    return tmp_path


@pytest.fixture()
def mock_keyring(monkeypatch: MonkeyPatch) -> dict[str, str]:
    """Replace the OS keyring with an in-memory dict.

    Patches keyring_read, keyring_write, and keyring_delete in
    switcher.auth.keyring_backend so no test ever touches the real keyring.

    Returns:
        The in-memory dict (service:key → value) for inspection.
    """
    store: dict[str, str] = {}

    def _read(service: str, key: str) -> str | None:
        return store.get(f"{service}:{key}")

    def _write(service: str, key: str, value: str) -> None:
        store[f"{service}:{key}"] = value

    def _delete(service: str, key: str) -> None:
        store.pop(f"{service}:{key}", None)

    import switcher.auth.keyring_backend as kb

    monkeypatch.setattr(kb, "keyring_read", _read)
    monkeypatch.setattr(kb, "keyring_write", _write)
    monkeypatch.setattr(kb, "keyring_delete", _delete)
    return store


@pytest.fixture()
def fake_gemini_dir(tmp_path: Path, monkeypatch: MonkeyPatch) -> Path:
    """Create a temp ~/.gemini directory and redirect get_gemini_dir() to it.

    Returns:
        Path to the fake Gemini config directory.
    """
    gemini_dir = tmp_path / ".gemini"
    gemini_dir.mkdir(parents=True, exist_ok=True)

    import switcher.auth.gemini_auth as ga
    import switcher.utils as utils

    monkeypatch.setattr(utils, "get_gemini_dir", lambda: gemini_dir)
    monkeypatch.setattr(ga, "get_gemini_dir", lambda: gemini_dir)
    return gemini_dir


@pytest.fixture()
def fake_codex_dir(tmp_path: Path, monkeypatch: MonkeyPatch) -> Path:
    """Create a temp ~/.codex directory and redirect get_codex_dir() to it.

    Returns:
        Path to the fake Codex config directory.
    """
    codex_dir = tmp_path / ".codex"
    codex_dir.mkdir(parents=True, exist_ok=True)

    import switcher.auth.codex_auth as ca
    import switcher.utils as utils

    monkeypatch.setattr(utils, "get_codex_dir", lambda: codex_dir)
    monkeypatch.setattr(ca, "get_codex_dir", lambda: codex_dir)
    return codex_dir


@pytest.fixture()
def sample_oauth_creds() -> dict[str, Any]:
    """Return a dict matching the oauth_creds.json format used by Gemini CLI."""
    return {
        "refreshToken": "r-token-abc",
        "accessToken": "a-token-xyz",
        "tokenType": "Bearer",
        "scope": "openid email profile",
        "expiresAt": 9_999_999_999_000,
    }


@pytest.fixture()
def sample_keyring_payload() -> dict[str, Any]:
    """Return a dict matching HybridTokenStorage keyring format."""
    return {
        "serverName": "main-account",
        "token": {
            "accessToken": "a-token-xyz",
            "refreshToken": "r-token-abc",
            "tokenType": "Bearer",
            "scope": "openid email profile",
            "expiresAt": 9_999_999_999_000,
        },
        "updatedAt": 1_700_000_000_000,
    }


@pytest.fixture()
def sample_auth_json() -> dict[str, Any]:
    """Return a dict matching the Codex auth.json format (API key variant)."""
    return {
        "OPENAI_API_KEY": "sk-test-key-abc",
        "tokens": None,
        "last_refresh": None,
    }


@pytest.fixture()
def sample_chatgpt_auth_json() -> dict[str, Any]:
    """Return a dict matching the Codex auth.json format (ChatGPT OAuth variant)."""
    return {
        "OPENAI_API_KEY": None,
        "tokens": {
            "refresh_token": "chatgpt-refresh-token",
            "access_token": "chatgpt-access-token",
        },
        "last_refresh": None,
    }


@pytest.fixture()
def mock_requests_post(monkeypatch: MonkeyPatch) -> MagicMock:
    """Patch requests.post with a MagicMock and return it for configuration."""
    mock = MagicMock()
    import switcher.health as health

    monkeypatch.setattr(health.requests, "post", mock)
    return mock


@pytest.fixture()
def mock_requests_get(monkeypatch: MonkeyPatch) -> MagicMock:
    """Patch requests.get with a MagicMock and return it for configuration."""
    mock = MagicMock()
    import switcher.health as health

    monkeypatch.setattr(health.requests, "get", mock)
    return mock
