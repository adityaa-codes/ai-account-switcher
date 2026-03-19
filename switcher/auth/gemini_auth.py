"""Gemini CLI credential handling — file, keyring, and cache management."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

from switcher.auth.keyring_backend import (
    detect_keyring_mode,
    keyring_delete,
    keyring_read,
    keyring_write,
)
from switcher.errors import AuthError, KeyringError
from switcher.utils import atomic_symlink, get_config_dir, get_gemini_dir

if TYPE_CHECKING:
    from pathlib import Path

logger = logging.getLogger("switcher.auth.gemini")

# Gemini CLI's own keyring coordinates
GEMINI_KEYRING_SERVICE = "gemini-cli-oauth"
GEMINI_KEYRING_KEY = "main-account"
GOOGLE_ACCOUNTS_FILE = "google_accounts.json"

# Switcher's keyring namespace for API keys
SWITCHER_GEMINI_SERVICE = "cli-switcher-gemini"


def _oauth_payload_has_token(payload: dict[str, Any]) -> bool:
    """Return True when oauth payload contains an access or refresh token."""
    token = payload.get("token", payload)
    if not isinstance(token, dict):
        return False

    return bool(
        token.get("refreshToken")
        or token.get("refresh_token")
        or token.get("accessToken")
        or token.get("access_token")
    )


def _read_json_object(path: Path) -> dict[str, Any] | None:
    """Read a JSON object from disk, returning None when invalid/unreadable."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _sync_oauth_from_keyring_blob(profile_dir: Path, keyring_blob: str) -> bool:
    """Write oauth_creds.json from a HybridTokenStorage keyring JSON blob."""
    try:
        keyring_json = json.loads(keyring_blob)
    except json.JSONDecodeError:
        return False
    if not isinstance(keyring_json, dict):
        return False

    oauth_creds = convert_from_keyring_format(keyring_json)
    if not _oauth_payload_has_token(oauth_creds):
        return False

    creds_file = profile_dir / "oauth_creds.json"
    creds_file.write_text(json.dumps(oauth_creds, indent=2) + "\n", encoding="utf-8")
    return True


def _restore_oauth_from_profile_keyring(profile_dir: Path) -> bool:
    """Recover oauth_creds.json from profile-local keyring backup when available."""
    keyring_file = profile_dir / "keyring_creds.json"
    if not keyring_file.exists():
        return False

    try:
        keyring_blob = keyring_file.read_text(encoding="utf-8")
    except OSError:
        return False

    return _sync_oauth_from_keyring_blob(profile_dir, keyring_blob)


def backup_current_credentials(profile_label: str) -> None:
    """Save current Gemini credentials back to the profile directory.

    Args:
        profile_label: Label of the currently active profile.
    """
    profile_dir = get_config_dir() / "profiles" / "gemini" / profile_label
    profile_dir.mkdir(parents=True, exist_ok=True)

    # Backup file credentials
    creds_path = get_gemini_dir() / "oauth_creds.json"
    if creds_path.exists():
        target = profile_dir / "oauth_creds.json"
        # Read through symlink and write actual content
        content = creds_path.read_text(encoding="utf-8")
        target.write_text(content, encoding="utf-8")
        logger.debug("Backed up oauth_creds.json for %s", profile_label)

    # Backup cached Google account identity shown in Gemini UI.
    accounts_path = get_gemini_dir() / GOOGLE_ACCOUNTS_FILE
    if accounts_path.exists():
        target = profile_dir / GOOGLE_ACCOUNTS_FILE
        content = accounts_path.read_text(encoding="utf-8")
        target.write_text(content, encoding="utf-8")
        logger.debug("Backed up %s for %s", GOOGLE_ACCOUNTS_FILE, profile_label)

    # Backup keyring credentials
    try:
        keyring_data = keyring_read(GEMINI_KEYRING_SERVICE, GEMINI_KEYRING_KEY)
        if keyring_data:
            keyring_file = profile_dir / "keyring_creds.json"
            keyring_file.write_text(keyring_data, encoding="utf-8")
            logger.debug("Backed up keyring credentials for %s", profile_label)

            # When Gemini stores tokens in keyring mode, oauth_creds.json can be
            # missing/stale. Persist a usable oauth_creds.json for future switches.
            creds_file = profile_dir / "oauth_creds.json"
            file_payload = (
                _read_json_object(creds_file) if creds_file.exists() else None
            )
            has_file_tokens = bool(
                file_payload and _oauth_payload_has_token(file_payload)
            )
            if not has_file_tokens and _sync_oauth_from_keyring_blob(
                profile_dir, keyring_data
            ):
                logger.info(
                    "Recovered oauth_creds.json from keyring backup for %s",
                    profile_label,
                )
    except KeyringError:
        logger.debug("No keyring credentials to backup for %s", profile_label)


def activate_oauth_profile(profile_dir: Path, storage_mode: str = "auto") -> None:
    """Activate a Gemini OAuth profile.

    Steps:
    1. Atomic symlink oauth_creds.json → ~/.gemini/oauth_creds.json
    2. Write to keyring in HybridTokenStorage format (if keyring mode)
    3. Clear token cache

    Args:
        profile_dir: Path to the profile directory containing oauth_creds.json.
        storage_mode: 'keyring', 'file', or 'auto'.
    """
    creds_file = profile_dir / "oauth_creds.json"
    creds_payload = _read_json_object(creds_file) if creds_file.exists() else None
    has_valid_file_tokens = bool(
        creds_payload and _oauth_payload_has_token(creds_payload)
    )
    if not has_valid_file_tokens and _restore_oauth_from_profile_keyring(profile_dir):
        creds_payload = _read_json_object(creds_file)
        has_valid_file_tokens = bool(
            creds_payload and _oauth_payload_has_token(creds_payload)
        )
        logger.info(
            "Recovered oauth_creds.json from profile keyring backup for %s",
            profile_dir.name,
        )

    if not creds_file.exists() or not has_valid_file_tokens:
        raise AuthError(
            f"Missing or invalid oauth_creds.json in {profile_dir}. "
            "Run Gemini OAuth enrollment for this profile."
        )
    assert creds_payload is not None

    gemini_dir = get_gemini_dir()
    gemini_dir.mkdir(parents=True, exist_ok=True)
    target = gemini_dir / "oauth_creds.json"

    # 1. Atomic symlink
    atomic_symlink(creds_file, target)
    logger.info("Symlinked oauth_creds.json → %s", creds_file)

    # Keep Gemini's displayed account identity in sync with the active profile.
    profile_accounts = profile_dir / GOOGLE_ACCOUNTS_FILE
    accounts_target = gemini_dir / GOOGLE_ACCOUNTS_FILE
    if profile_accounts.exists():
        atomic_symlink(profile_accounts, accounts_target)
        logger.info("Symlinked %s → %s", GOOGLE_ACCOUNTS_FILE, profile_accounts)
    else:
        accounts_target.unlink(missing_ok=True)
        logger.debug("Removed stale %s", GOOGLE_ACCOUNTS_FILE)

    # 2. Update keyring
    mode = detect_keyring_mode(storage_mode)
    if mode == "keyring":
        try:
            keyring_json = convert_to_keyring_format(creds_payload)
            keyring_delete(GEMINI_KEYRING_SERVICE, GEMINI_KEYRING_KEY)
            keyring_write(
                GEMINI_KEYRING_SERVICE, GEMINI_KEYRING_KEY, json.dumps(keyring_json)
            )
            logger.info("Updated Gemini keyring entry")
        except KeyringError:
            logger.warning("Keyring write failed — file-only mode for this switch")

    # 3. Clear cache
    clear_gemini_cache()

    # 4. Remove stale Gemini API-key exports while preserving Codex env state.
    from switcher.auth.codex_auth import write_env_sh

    write_env_sh(gemini_key=None, codex_key=None, clear_gemini=True)


def activate_apikey_profile(api_key: str, label: str) -> None:
    """Activate a Gemini API key profile by writing to env.sh.

    Args:
        api_key: The Gemini API key string.
        label: Profile label for logging.
    """
    from switcher.auth.codex_auth import write_env_sh

    write_env_sh(gemini_key=api_key, codex_key=None)
    logger.info("Activated Gemini API key profile: %s", label)


def clear_gemini_cache() -> None:
    """Delete Gemini CLI's token cache files."""
    gemini_dir = get_gemini_dir()
    cache_files = [
        gemini_dir / "mcp-oauth-tokens.json",
    ]
    for cache_file in cache_files:
        if cache_file.exists():
            cache_file.unlink()
            logger.debug("Deleted cache: %s", cache_file)


def convert_to_keyring_format(oauth_creds: dict[str, Any]) -> dict[str, Any]:
    """Convert oauth_creds.json format to HybridTokenStorage keyring format.

    Args:
        oauth_creds: Parsed contents of oauth_creds.json.

    Returns:
        Dict matching Gemini CLI's HybridTokenStorage schema.
    """
    import time

    # oauth_creds.json may have camelCase or snake_case keys
    token = oauth_creds.get("token", oauth_creds)

    return {
        "serverName": "main-account",
        "token": {
            "accessToken": token.get("accessToken", token.get("access_token", "")),
            "refreshToken": token.get("refreshToken", token.get("refresh_token", "")),
            "tokenType": token.get("tokenType", token.get("token_type", "Bearer")),
            "scope": token.get("scope", ""),
            "expiresAt": token.get("expiresAt", token.get("expires_at", 0)),
        },
        "updatedAt": int(time.time() * 1000),
    }


def convert_from_keyring_format(keyring_json: dict[str, Any]) -> dict[str, Any]:
    """Convert HybridTokenStorage keyring format to oauth_creds.json format.

    Args:
        keyring_json: Parsed keyring credential data.

    Returns:
        Dict suitable for writing to oauth_creds.json.
    """
    token = keyring_json.get("token", {})
    return {
        "accessToken": token.get("accessToken", ""),
        "refreshToken": token.get("refreshToken", ""),
        "tokenType": token.get("tokenType", "Bearer"),
        "scope": token.get("scope", ""),
        "expiresAt": token.get("expiresAt", 0),
    }
