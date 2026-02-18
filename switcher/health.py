"""Profile health checking — token and API key validation."""

from __future__ import annotations

import json
import logging
import re
import shutil
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

import requests

from switcher.profiles.base import save_meta

if TYPE_CHECKING:
    from switcher.profiles.base import Profile

logger = logging.getLogger("switcher.health")

# Google OAuth token endpoint
_GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
# Known Google OAuth client credentials used by Gemini CLI over time.
_KNOWN_GOOGLE_OAUTH_CLIENTS: list[tuple[str, str]] = [
    (
        "681255809395-oo8ft2oprdrnp9e3aqf6av3hmdib135j.apps.googleusercontent.com",
        "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",
    ),
    (
        "710733570747-4bm2qi30m3sj1e2t6ri1urlb80sqmnml.apps.googleusercontent.com",
        "GOCSPX-bwSFJu80JKsALpWxFjJnOk4R",
    ),
]

# Gemini API key validation endpoint
_GEMINI_MODELS_URL = "https://generativelanguage.googleapis.com/v1/models"

# OpenAI API validation endpoint
_OPENAI_MODELS_URL = "https://api.openai.com/v1/models"

# OpenAI OAuth token endpoint
_OPENAI_TOKEN_URL = "https://auth.openai.com/oauth/token"

_TIMEOUT = 10  # seconds


def _discover_gemini_oauth_client() -> tuple[str, str] | None:
    """Read OAuth client credentials from installed Gemini CLI, if available."""
    gemini_bin = shutil.which("gemini")
    if not gemini_bin:
        return None

    resolved = Path(gemini_bin).resolve()
    # /.../gemini-cli/dist/index.js -> /.../gemini-cli
    package_root = resolved.parent.parent
    oauth2_js = (
        package_root
        / "node_modules"
        / "@google"
        / "gemini-cli-core"
        / "dist"
        / "src"
        / "code_assist"
        / "oauth2.js"
    )
    if not oauth2_js.exists():
        return None

    try:
        content = oauth2_js.read_text(encoding="utf-8")
    except OSError:
        return None

    id_match = re.search(r"OAUTH_CLIENT_ID = '([^']+)'", content)
    secret_match = re.search(r"OAUTH_CLIENT_SECRET = '([^']+)'", content)
    if not id_match or not secret_match:
        return None
    return id_match.group(1), secret_match.group(1)


def _google_oauth_clients() -> list[tuple[str, str]]:
    """Return ordered OAuth clients to try for Gemini refresh checks."""
    clients: list[tuple[str, str]] = []

    discovered = _discover_gemini_oauth_client()
    if discovered:
        clients.append(discovered)

    for candidate in _KNOWN_GOOGLE_OAUTH_CLIENTS:
        if candidate not in clients:
            clients.append(candidate)

    return clients


def _oauth_error_detail(resp: requests.Response) -> tuple[str, str]:
    """Extract OAuth error code/description from a response body."""
    try:
        payload = resp.json()
    except (ValueError, json.JSONDecodeError):
        return "", ""

    if not isinstance(payload, dict):
        return "", ""

    error = str(payload.get("error", "")).strip()
    description = str(payload.get("error_description", "")).strip()
    return error, description


def _format_refresh_error(resp: requests.Response) -> str:
    """Create a human-readable refresh failure message."""
    error, description = _oauth_error_detail(resp)
    detail = f"Refresh failed: HTTP {resp.status_code}"
    if error:
        detail += f" ({error})"
    if description:
        detail += f" - {description}"
    return detail


def interpret_http_status(status_code: int) -> str:
    """Map an HTTP status code to a health status string.

    Args:
        status_code: HTTP response status code.

    Returns:
        One of 'valid', 'expired', 'revoked', 'unknown'.
    """
    if status_code == 200:
        return "valid"
    if status_code in (401, 403):
        return "revoked"
    if status_code == 429:
        # Rate limited but key/token is valid
        return "valid"
    return "unknown"


def check_gemini_oauth(profile_dir: Path) -> tuple[str, str]:
    """Validate a Gemini OAuth profile by attempting token refresh.

    Args:
        profile_dir: Path to profile directory with oauth_creds.json.

    Returns:
        Tuple of (health_status, detail_message).
    """
    creds_path = profile_dir / "oauth_creds.json"
    if not creds_path.exists():
        return "expired", "Missing oauth_creds.json"

    try:
        with creds_path.open("r", encoding="utf-8") as f:
            creds: dict[str, Any] = json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        return "expired", f"Cannot parse credentials: {exc}"

    # Extract refresh token (handle both formats)
    token = creds.get("token", creds)
    refresh_token = token.get("refreshToken", token.get("refresh_token"))
    if not refresh_token:
        return "expired", "No refresh token found"

    # Check if access token is still valid (not expired)
    expires_at = token.get("expiresAt", token.get("expires_at", 0))
    now_ms = int(time.time() * 1000)
    if isinstance(expires_at, int) and expires_at > 0:
        remaining_hours = (expires_at - now_ms) / (1000 * 3600)
        if 0 < remaining_hours < 24:
            return "expiring", (f"Token expires in {remaining_hours:.1f} hours")

    # Attempt refresh with discovered/current and legacy Gemini OAuth clients.
    try:
        responses: list[requests.Response] = []
        for client_id, client_secret in _google_oauth_clients():
            resp = requests.post(
                _GOOGLE_TOKEN_URL,
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                    "client_id": client_id,
                    "client_secret": client_secret,
                },
                timeout=_TIMEOUT,
            )
            if resp.status_code == 200:
                return "valid", "Token refreshed successfully"
            responses.append(resp)

            # Some environments treat Gemini as a public OAuth client and reject
            # client_secret. Retry once without secret before classifying.
            error, _ = _oauth_error_detail(resp)
            if resp.status_code == 401 and error in (
                "invalid_client",
                "unauthorized_client",
            ):
                retry = requests.post(
                    _GOOGLE_TOKEN_URL,
                    data={
                        "grant_type": "refresh_token",
                        "refresh_token": refresh_token,
                        "client_id": client_id,
                    },
                    timeout=_TIMEOUT,
                )
                if retry.status_code == 200:
                    return "valid", "Token refreshed successfully"
                responses.append(retry)

        if not responses:
            return "unknown", "Refresh check did not produce a response"

        for resp in responses:
            error, _ = _oauth_error_detail(resp)
            if error == "invalid_grant":
                return "revoked", _format_refresh_error(resp)

        for resp in responses:
            error, _ = _oauth_error_detail(resp)
            if error in ("invalid_client", "unauthorized_client"):
                continue
            status = interpret_http_status(resp.status_code)
            return status, _format_refresh_error(resp)

        # Only invalid_client/unauthorized_client responses were seen.
        return "unknown", _format_refresh_error(responses[0])
    except requests.RequestException as exc:
        return "unknown", f"Network error: {exc}"


def check_gemini_apikey(api_key: str) -> tuple[str, str]:
    """Validate a Gemini API key with a minimal models.list call.

    Args:
        api_key: The Gemini API key string.

    Returns:
        Tuple of (health_status, detail_message).
    """
    try:
        resp = requests.get(
            _GEMINI_MODELS_URL,
            params={"key": api_key, "pageSize": "1"},
            timeout=_TIMEOUT,
        )
        status = interpret_http_status(resp.status_code)
        if status == "valid":
            return "valid", "API key is valid"
        return status, f"API returned HTTP {resp.status_code}"
    except requests.RequestException as exc:
        return "unknown", f"Network error: {exc}"


def check_codex_apikey(api_key: str) -> tuple[str, str]:
    """Validate an OpenAI API key with a minimal models call.

    Args:
        api_key: The OpenAI API key string.

    Returns:
        Tuple of (health_status, detail_message).
    """
    try:
        resp = requests.get(
            _OPENAI_MODELS_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            params={"limit": "1"},
            timeout=_TIMEOUT,
        )
        status = interpret_http_status(resp.status_code)
        if status == "valid":
            return "valid", "API key is valid"
        return status, f"API returned HTTP {resp.status_code}"
    except requests.RequestException as exc:
        return "unknown", f"Network error: {exc}"


def check_codex_chatgpt(
    profile_dir: Path,
) -> tuple[str, str]:
    """Validate a Codex ChatGPT OAuth profile by attempting refresh.

    Args:
        profile_dir: Path to profile directory with auth.json.

    Returns:
        Tuple of (health_status, detail_message).
    """
    auth_path = profile_dir / "auth.json"
    if not auth_path.exists():
        return "expired", "Missing auth.json"

    try:
        with auth_path.open("r", encoding="utf-8") as f:
            data: dict[str, Any] = json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        return "expired", f"Cannot parse auth.json: {exc}"

    tokens = data.get("tokens")
    if not tokens or not isinstance(tokens, dict):
        return "expired", "No tokens found in auth.json"

    refresh_token = tokens.get("refresh_token")
    if not refresh_token:
        return "expired", "No refresh token found"

    try:
        resp = requests.post(
            _OPENAI_TOKEN_URL,
            json={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            },
            timeout=_TIMEOUT,
        )
        if resp.status_code == 200:
            return "valid", "Token refreshed successfully"
        status = interpret_http_status(resp.status_code)
        return status, f"Refresh failed: HTTP {resp.status_code}"
    except requests.RequestException as exc:
        return "unknown", f"Network error: {exc}"


def check_profile(cli_name: str, profile: Profile) -> tuple[str, str]:
    """Dispatch health check based on CLI and auth type.

    Args:
        cli_name: 'gemini' or 'codex'.
        profile: The Profile object to check.

    Returns:
        Tuple of (health_status, detail_message).
    """
    auth_type = profile.meta.get("auth_type", profile.auth_type)

    if cli_name == "gemini":
        if auth_type == "oauth":
            return check_gemini_oauth(profile.path)
        if auth_type == "apikey":
            key_file = profile.path / "api_key.txt"
            if not key_file.exists():
                return "expired", "Missing api_key.txt"
            api_key = key_file.read_text(encoding="utf-8").strip()
            return check_gemini_apikey(api_key)

    if cli_name == "codex":
        if auth_type == "apikey":
            auth_file = profile.path / "auth.json"
            if not auth_file.exists():
                return "expired", "Missing auth.json"
            try:
                with auth_file.open("r", encoding="utf-8") as f:
                    data = json.load(f)
                api_key = data.get("OPENAI_API_KEY", "")
            except (json.JSONDecodeError, OSError):
                return "expired", "Cannot parse auth.json"
            if not api_key:
                return "expired", "No API key in auth.json"
            return check_codex_apikey(api_key)
        if auth_type == "chatgpt":
            return check_codex_chatgpt(profile.path)

    return "unknown", f"Unknown auth type: {auth_type}"


def check_all_profiles(
    cli_name: str, profiles: list[Profile]
) -> list[tuple[Profile, str, str]]:
    """Run health checks on all profiles and update meta.json.

    Args:
        cli_name: 'gemini' or 'codex'.
        profiles: List of Profile objects to check.

    Returns:
        List of (profile, status, detail) tuples.
    """
    from datetime import datetime, timezone

    results: list[tuple[Profile, str, str]] = []
    for profile in profiles:
        logger.info("Checking %s/%s...", cli_name, profile.label)
        status, detail = check_profile(cli_name, profile)

        # Update meta
        profile.meta["health_status"] = status
        profile.meta["health_detail"] = detail
        profile.meta["last_health_check"] = datetime.now(timezone.utc).isoformat()
        save_meta(profile.path, profile.meta)

        results.append((profile, status, detail))
        logger.info("  %s: %s — %s", profile.label, status, detail)

    return results
