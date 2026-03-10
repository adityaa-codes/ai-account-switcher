#!/usr/bin/env python3
"""Gemini BeforeAgent hook — pre-check quota and proactively switch profiles.

This script runs as a subprocess of Gemini CLI before every agent request.
It reads JSON from stdin, checks cached quota data, and switches profiles
if the active profile's quota is below the configured threshold.

IMPORTANT: This script must NEVER exit non-zero or output invalid JSON.
Any error → output {} and exit 0.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

# Undocumented Google APIs for quota checking
LOAD_CODE_ASSIST_URL = "https://cloudcode-pa.googleapis.com/v1internal:loadCodeAssist"
RETRIEVE_QUOTA_URL = "https://cloudcode-pa.googleapis.com/v1internal:retrieveUserQuota"


def _output(data: dict) -> None:  # type: ignore[type-arg]
    """Write JSON to stdout and exit."""
    json.dump(data, sys.stdout)
    sys.stdout.write("\n")
    sys.stdout.flush()


def _get_access_token(profile_dir: Path) -> str | None:
    """Read access_token from profile's oauth_creds.json."""
    creds_file = profile_dir / "oauth_creds.json"
    if not creds_file.exists():
        return None
    try:
        data = json.loads(creds_file.read_text())
        # Handle both flat and nested token formats
        if "access_token" in data:
            return str(data["access_token"])
        if "token" in data and isinstance(data["token"], dict):
            return str(data["token"].get("accessToken", ""))
        return None
    except (json.JSONDecodeError, KeyError):
        return None


def _refresh_and_get_token(profile_dir: Path) -> str | None:
    """Try to refresh the token and return a valid access token."""
    import requests

    creds_file = profile_dir / "oauth_creds.json"
    if not creds_file.exists():
        return None

    try:
        data = json.loads(creds_file.read_text())
        refresh_token = None
        if "refresh_token" in data:
            refresh_token = data["refresh_token"]
        elif "token" in data and isinstance(data["token"], dict):
            refresh_token = data["token"].get("refreshToken")

        if not refresh_token:
            return _get_access_token(profile_dir)

        # Try each known Gemini CLI OAuth client in order
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
        from switcher.health import _KNOWN_GOOGLE_OAUTH_CLIENTS

        for client_id, client_secret in _KNOWN_GOOGLE_OAUTH_CLIENTS:
            resp = requests.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "refresh_token": refresh_token,
                    "grant_type": "refresh_token",
                },
                timeout=5,
            )
            if resp.status_code == 200:
                return str(resp.json().get("access_token", ""))
    except Exception:
        pass

    return _get_access_token(profile_dir)


def _fetch_quota(access_token: str) -> dict | None:  # type: ignore[type-arg]
    """Fetch quota from undocumented Google APIs.

    Returns dict mapping model names to remaining fraction (0.0-1.0),
    or None on failure.
    """
    import requests

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }

    try:
        # Step 1: Get project ID
        resp = requests.post(
            LOAD_CODE_ASSIST_URL,
            headers=headers,
            json={
                "metadata": {
                    "ideType": "GEMINI_CLI",
                    "platform": "PLATFORM_UNSPECIFIED",
                    "pluginType": "GEMINI",
                },
                "mode": "HEALTH_CHECK",
            },
            timeout=5,
        )
        if resp.status_code != 200:
            return None

        project_id = resp.json().get("cloudaicompanionProject", "")
        if not project_id:
            return None

        # Step 2: Get quota
        resp = requests.post(
            RETRIEVE_QUOTA_URL,
            headers=headers,
            json={"cloudaicompanionProject": project_id},
            timeout=5,
        )
        if resp.status_code != 200:
            return None

        quotas = {}
        for q in resp.json().get("userQuota", []):
            model_name = q.get("modelName", "unknown")
            remaining = q.get("remainingFraction", 1.0)
            quotas[model_name] = float(remaining)

        return quotas

    except Exception:
        return None


def _load_quota_cache(cache_file: Path) -> dict | None:  # type: ignore[type-arg]
    """Load cached quota data if not expired."""
    if not cache_file.exists():
        return None
    try:
        data = json.loads(cache_file.read_text())
        cached_at = data.get("cached_at", 0)
        ttl = data.get("ttl", 300)  # 5 minutes default
        if time.time() - cached_at < ttl:
            quotas: dict[str, object] | None = data.get("quotas")
            return quotas
    except (json.JSONDecodeError, KeyError):
        pass
    return None


def _save_quota_cache(
    cache_file: Path,
    quotas: dict,  # type: ignore[type-arg]
    ttl: int = 300,
) -> None:
    """Save quota data to cache file."""
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(
        json.dumps(
            {
                "cached_at": time.time(),
                "ttl": ttl,
                "quotas": quotas,
            }
        )
    )


def _should_switch(
    quotas: dict,  # type: ignore[type-arg]
    threshold: float,
    strategy: str,
) -> bool:
    """Determine if profile switch is needed based on quota and strategy."""
    if not quotas:
        return False

    fractions = list(quotas.values())

    if strategy == "conservative":
        # Switch only if ALL models below threshold
        return all(f < threshold for f in fractions)
    else:
        # gemini3-first: switch if ANY model below threshold
        return any(f < threshold for f in fractions)


def main() -> None:
    """BeforeAgent hook entry point."""
    try:
        # Parse stdin
        _input_data = json.load(sys.stdin)

        # Gemini CLI sets stopHookActive when it has already stopped the agent
        # loop. Respect it and do nothing — attempting a switch here would hang.
        if _input_data.get("stopHookActive"):
            _output({})
            return

        # Load config
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
        from switcher.config import load_config
        from switcher.state import (
            clear_quota_error_flag,
            get_active_profile,
            get_quota_error_flag,
        )
        from switcher.utils import get_config_dir

        config = load_config()
        ar = config["auto_rotate"]

        if not ar["enabled"] or not ar.get("pre_check", True):
            _output({})
            return

        threshold = ar.get("threshold_percent", 10) / 100.0
        strategy = ar.get("strategy", "conservative")
        cache_minutes = ar.get("cache_minutes", 5)

        # Get active profile directory
        active = get_active_profile("gemini")
        if not active:
            _output({})
            return

        profiles_dir = get_config_dir() / "profiles" / "gemini" / active
        if not profiles_dir.exists():
            _output({})
            return

        # If AfterAgent wrote a handoff flag, trust it and skip the API call.
        if get_quota_error_flag("gemini"):
            clear_quota_error_flag("gemini")
            _output({})
            return

        # Check quota cache
        cache_file = get_config_dir() / "cache" / "quota_gemini.json"
        quotas = _load_quota_cache(cache_file)

        if quotas is None:
            # Cache expired — fetch fresh quota
            access_token = _refresh_and_get_token(profiles_dir)
            if not access_token:
                _output({})
                return

            quotas = _fetch_quota(access_token)
            if quotas is None:
                _output({})
                return

            _save_quota_cache(cache_file, quotas, ttl=cache_minutes * 60)

        # Decide if switch is needed
        if not _should_switch(quotas, threshold, strategy):
            _output({})
            return

        # Switch to next profile
        import subprocess

        from switcher.hooks.gemini_after_agent import _find_switcher

        switcher_cmd = _find_switcher()
        result = subprocess.run(
            [sys.executable, switcher_cmd, "gemini", "next"],
            capture_output=True,
            text=True,
            timeout=8,
        )

        if result.returncode != 0:
            _output({})
            return

        new_profile = get_active_profile("gemini") or "next account"
        _output(
            {
                "systemMessage": (
                    f"\u26a1 Quota low — switched to {new_profile}. "
                    "Please /clear and retry."
                ),
            }
        )

    except Exception:
        # Never crash the parent CLI
        _output({})


if __name__ == "__main__":
    main()
