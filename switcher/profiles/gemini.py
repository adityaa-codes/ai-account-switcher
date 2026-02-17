"""Gemini CLI profile manager — list, add, remove, switch, import, export."""

from __future__ import annotations

import json
import logging
import shutil
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from switcher.auth.gemini_auth import (
    activate_apikey_profile,
    activate_oauth_profile,
    backup_current_credentials,
)
from switcher.config import load_config
from switcher.errors import AuthError, ProfileCorruptError, ProfileNotFoundError
from switcher.profiles.base import Profile, ProfileManager, load_meta, save_meta
from switcher.state import get_active_profile, set_active_profile
from switcher.utils import get_config_dir, get_gemini_dir

if TYPE_CHECKING:
    from pathlib import Path

logger = logging.getLogger("switcher.profiles.gemini")


class GeminiProfileManager(ProfileManager):
    """Manage Gemini CLI authentication profiles."""

    def __init__(self) -> None:
        super().__init__(
            cli_name="gemini",
            profiles_dir=get_config_dir() / "profiles" / "gemini",
            target_dir=get_gemini_dir(),
        )
        self.profiles_dir.mkdir(parents=True, exist_ok=True)

    def list_profiles(self) -> list[Profile]:
        """List all Gemini profiles, sorted by label."""
        active = get_active_profile("gemini")
        profiles: list[Profile] = []

        if not self.profiles_dir.exists():
            return profiles

        for entry in sorted(self.profiles_dir.iterdir()):
            if not entry.is_dir():
                continue
            meta = load_meta(entry)
            profiles.append(
                Profile(
                    label=entry.name,
                    auth_type=meta.get("auth_type", "unknown"),
                    path=entry,
                    is_active=(entry.name == active),
                    meta=meta,
                )
            )
        return profiles

    def get_profile(self, identifier: str) -> Profile:
        """Get a Gemini profile by index or label."""
        return self._resolve_identifier(identifier)

    def add_profile(self, label: str, auth_type: str) -> Profile:
        """Add a new Gemini profile.

        Args:
            label: Email or descriptive name.
            auth_type: 'oauth' or 'apikey'.

        Returns:
            The newly created Profile.
        """
        profile_dir = self.profiles_dir / label
        if profile_dir.exists():
            raise AuthError(f"Profile '{label}' already exists")

        profile_dir.mkdir(parents=True)
        meta: dict[str, Any] = {
            "label": label,
            "auth_type": auth_type,
            "added_at": datetime.now(timezone.utc).isoformat(),
            "last_used": None,
            "last_health_check": None,
            "health_status": "unknown",
            "health_detail": None,
            "notes": "",
        }
        save_meta(profile_dir, meta)

        if auth_type == "oauth":
            # If Gemini CLI already has credentials, offer to import them
            existing_creds = get_gemini_dir() / "oauth_creds.json"
            if existing_creds.exists() and not get_active_profile("gemini"):
                content = existing_creds.read_text(encoding="utf-8")
                (profile_dir / "oauth_creds.json").write_text(content, encoding="utf-8")
                logger.info("Imported existing Gemini OAuth credentials for %s", label)

        logger.info("Created Gemini profile: %s (%s)", label, auth_type)
        return Profile(label=label, auth_type=auth_type, path=profile_dir, meta=meta)

    def remove_profile(self, identifier: str) -> str:
        """Remove a Gemini profile."""
        profile = self._resolve_identifier(identifier)

        if profile.is_active:
            raise AuthError(
                f"Cannot remove active profile '{profile.label}'. "
                "Switch to another profile first."
            )

        shutil.rmtree(profile.path)
        logger.info("Removed Gemini profile: %s", profile.label)
        return profile.label

    def switch_to(self, identifier: str) -> str:
        """Switch to a Gemini profile by index or label."""
        profile = self._resolve_identifier(identifier)
        config = load_config()
        storage_mode = config["general"]["storage_mode"]

        # Backup current credentials
        current = get_active_profile("gemini")
        if current and current != profile.label:
            try:
                backup_current_credentials(current)
            except Exception:
                logger.warning("Failed to backup current credentials", exc_info=True)

        # Activate based on auth type
        if profile.meta.get("auth_type") == "apikey":
            key_file = profile.path / "api_key.txt"
            if not key_file.exists():
                raise ProfileCorruptError(
                    f"Missing api_key.txt in profile '{profile.label}'"
                )
            api_key = key_file.read_text(encoding="utf-8").strip()
            activate_apikey_profile(api_key, profile.label)
        else:
            activate_oauth_profile(profile.path, storage_mode)

        # Update state and meta
        set_active_profile("gemini", profile.label)
        profile.meta["last_used"] = datetime.now(timezone.utc).isoformat()
        save_meta(profile.path, profile.meta)

        logger.info("Switched Gemini to: %s", profile.label)
        return profile.label

    def switch_next(self) -> str:
        """Rotate to the next Gemini profile."""
        profiles = self.list_profiles()
        if len(profiles) < 2:
            raise ProfileNotFoundError(
                f"Need at least 2 profiles to rotate. Currently have {len(profiles)}."
            )

        current = get_active_profile("gemini")
        current_idx = 0
        for i, p in enumerate(profiles):
            if p.label == current:
                current_idx = i
                break

        next_idx = (current_idx + 1) % len(profiles)
        return self.switch_to(profiles[next_idx].label)

    def import_credentials(self, path: Path, label: str) -> Profile:
        """Import a credentials file as a new Gemini profile.

        Args:
            path: Path to oauth_creds.json or a file containing an API key.
            label: Label for the new profile.

        Returns:
            The created Profile.
        """
        if not path.exists():
            raise AuthError(f"File not found: {path}")

        # Detect auth type from file content
        auth_type = self._detect_import_type(path)

        profile = self.add_profile(label, auth_type)

        if auth_type == "oauth":
            shutil.copy2(path, profile.path / "oauth_creds.json")
        elif auth_type == "apikey":
            content = path.read_text(encoding="utf-8").strip()
            (profile.path / "api_key.txt").write_text(content + "\n", encoding="utf-8")

        profile.meta["auth_type"] = auth_type
        save_meta(profile.path, profile.meta)
        logger.info("Imported %s credentials as '%s'", auth_type, label)
        return profile

    def export_profile(self, identifier: str, dest: Path) -> Path:
        """Export a Gemini profile's credentials to a file.

        Args:
            identifier: 1-based index or label.
            dest: Destination path (file or directory).

        Returns:
            The path of the exported file.
        """
        profile = self._resolve_identifier(identifier)

        # Determine the credential file to export
        if profile.auth_type == "oauth":
            src = profile.path / "oauth_creds.json"
            default_name = f"{profile.label}_oauth_creds.json"
        else:
            src = profile.path / "api_key.txt"
            default_name = f"{profile.label}_api_key.txt"

        if not src.exists():
            raise AuthError(f"No credential file found for profile '{profile.label}'")

        # Resolve dest — if it's a directory, use default filename
        out = dest / default_name if dest.is_dir() else dest

        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, out)
        logger.info("Exported '%s' → %s", profile.label, out)
        return out

    @staticmethod
    def _detect_import_type(path: Path) -> str:
        """Detect whether a file contains OAuth credentials or an API key."""
        try:
            with path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            # OAuth creds have token fields
            if any(
                k in data
                for k in ("refreshToken", "refresh_token", "accessToken", "token")
            ):
                return "oauth"
        except (json.JSONDecodeError, OSError):
            pass

        # Treat as API key
        content = path.read_text(encoding="utf-8").strip()
        if content.startswith("AIza"):
            return "apikey"

        return "apikey"  # Default to API key for plain text files
