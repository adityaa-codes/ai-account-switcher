"""Helpers for discovering existing local Gemini/Codex auth state."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from switcher.auth import gemini_auth
from switcher.auth.codex_auth import detect_auth_type
from switcher.auth.keyring_backend import detect_keyring_mode, keyring_read
from switcher.errors import AuthError
from switcher.utils import get_codex_dir, get_gemini_dir

if TYPE_CHECKING:
    from pathlib import Path

    from switcher.profiles.base import Profile


class _ImportManager(Protocol):
    """Protocol for profile manager methods used during auth adoption."""

    def list_profiles(self) -> list[Profile]:
        """List existing profiles."""

    def import_credentials(self, path: Path, label: str) -> Profile:
        """Import auth credentials into a newly created profile."""


@dataclass(slots=True)
class AuthDiscoveryResult:
    """Result for a discovered auth file."""

    cli_name: str
    path: Path
    found: bool
    valid: bool
    reason: str
    detected_auth_type: str | None = None


def _has_gemini_oauth_tokens(payload: dict[str, object]) -> bool:
    """Return True when Gemini oauth payload contains token fields."""
    token = payload.get("token", payload)
    if not isinstance(token, dict):
        return False
    return bool(
        token.get("refreshToken")
        or token.get("refresh_token")
        or token.get("accessToken")
        or token.get("access_token")
    )


def discover_gemini_auth(path: Path | None = None) -> AuthDiscoveryResult:
    """Discover and validate an existing Gemini oauth_creds.json file."""
    auth_path = path if path is not None else get_gemini_dir() / "oauth_creds.json"
    if not auth_path.exists():
        keyring_blob = None
        try:
            keyring_blob = keyring_read(
                gemini_auth.GEMINI_KEYRING_SERVICE,
                gemini_auth.GEMINI_KEYRING_KEY,
            )
        except Exception:
            keyring_blob = None
        if keyring_blob:
            return AuthDiscoveryResult(
                cli_name="gemini",
                path=auth_path,
                found=True,
                valid=False,
                reason=(
                    "Gemini credentials appear to exist in keyring-only mode; "
                    "run Gemini once to sync oauth_creds.json, then re-run discover"
                ),
                detected_auth_type="oauth",
            )
        return AuthDiscoveryResult(
            cli_name="gemini",
            path=auth_path,
            found=False,
            valid=False,
            reason="Gemini oauth_creds.json not found",
            detected_auth_type=None,
        )

    try:
        payload = json.loads(auth_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return AuthDiscoveryResult(
            cli_name="gemini",
            path=auth_path,
            found=True,
            valid=False,
            reason="Gemini oauth_creds.json is not valid JSON",
            detected_auth_type=None,
        )

    if not isinstance(payload, dict) or not _has_gemini_oauth_tokens(payload):
        return AuthDiscoveryResult(
            cli_name="gemini",
            path=auth_path,
            found=True,
            valid=False,
            reason="Gemini oauth_creds.json is missing OAuth token fields",
            detected_auth_type=None,
        )

    return AuthDiscoveryResult(
        cli_name="gemini",
        path=auth_path,
        found=True,
        valid=True,
        reason="Gemini OAuth credentials discovered",
        detected_auth_type="oauth",
    )


def discover_codex_auth(path: Path | None = None) -> AuthDiscoveryResult:
    """Discover and validate an existing Codex auth.json file."""
    auth_path = path if path is not None else get_codex_dir() / "auth.json"
    if not auth_path.exists():
        if detect_keyring_mode("auto") == "keyring":
            return AuthDiscoveryResult(
                cli_name="codex",
                path=auth_path,
                found=True,
                valid=False,
                reason=(
                    "Codex auth.json not found; credentials may be keyring-backed. "
                    "Run codex login status/export then re-run discover"
                ),
                detected_auth_type=None,
            )
        return AuthDiscoveryResult(
            cli_name="codex",
            path=auth_path,
            found=False,
            valid=False,
            reason="Codex auth.json not found",
            detected_auth_type=None,
        )

    try:
        detected_auth_type = detect_auth_type(auth_path)
    except AuthError as exc:
        return AuthDiscoveryResult(
            cli_name="codex",
            path=auth_path,
            found=True,
            valid=False,
            reason=f"Codex auth.json is invalid: {exc}",
            detected_auth_type=None,
        )

    return AuthDiscoveryResult(
        cli_name="codex",
        path=auth_path,
        found=True,
        valid=True,
        reason="Codex credentials discovered",
        detected_auth_type=detected_auth_type,
    )


def discover_existing_auth() -> dict[str, AuthDiscoveryResult]:
    """Discover existing auth files for both supported CLIs."""
    gemini = discover_gemini_auth()
    codex = discover_codex_auth()
    return {"gemini": gemini, "codex": codex}


def _ensure_unique_label(base: str, existing: set[str]) -> str:
    """Return a label unique against *existing* using stable numeric suffixes."""
    if base not in existing:
        return base
    i = 2
    while f"{base}-{i}" in existing:
        i += 1
    return f"{base}-{i}"


def default_adopt_label(
    cli_name: str,
    existing_labels: set[str],
) -> str:
    """Return deterministic default label for adopted credentials."""
    base = {
        "gemini": "personal-gemini",
        "codex": "personal-codex",
    }.get(cli_name, f"personal-{cli_name}")
    return _ensure_unique_label(base, existing_labels)


def adopt_discovered_auth(
    result: AuthDiscoveryResult,
    manager: _ImportManager,
    label: str | None = None,
) -> Profile | None:
    """Import discovered credentials using a non-destructive copy-based flow.

    Returns the imported profile, or ``None`` when discovery was not valid.
    """
    if not result.found or not result.valid:
        return None

    existing_labels = {p.label for p in manager.list_profiles()}
    target_label = label or default_adopt_label(result.cli_name, existing_labels)
    return manager.import_credentials(result.path, target_label)
