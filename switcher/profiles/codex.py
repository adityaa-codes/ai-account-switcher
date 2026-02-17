"""Codex CLI profile manager — list, add, remove, switch, import."""

from __future__ import annotations

import json
import logging
import shutil
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from switcher.auth.codex_auth import (
    activate_apikey_profile,
    activate_chatgpt_profile,
    detect_auth_type,
)
from switcher.errors import AuthError, ProfileCorruptError, ProfileNotFoundError
from switcher.profiles.base import Profile, ProfileManager, load_meta, save_meta
from switcher.state import get_active_profile, set_active_profile
from switcher.utils import get_codex_dir, get_config_dir

if TYPE_CHECKING:
    from pathlib import Path

logger = logging.getLogger("switcher.profiles.codex")


class CodexProfileManager(ProfileManager):
    """Manage Codex CLI authentication profiles."""

    def __init__(self) -> None:
        super().__init__(
            cli_name="codex",
            profiles_dir=get_config_dir() / "profiles" / "codex",
            target_dir=get_codex_dir(),
        )
        self.profiles_dir.mkdir(parents=True, exist_ok=True)

    def list_profiles(self) -> list[Profile]:
        """List all Codex profiles, sorted by label."""
        active = get_active_profile("codex")
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
        """Get a Codex profile by index or label."""
        return self._resolve_identifier(identifier)

    def add_profile(self, label: str, auth_type: str) -> Profile:
        """Add a new Codex profile.

        Args:
            label: Descriptive name.
            auth_type: 'apikey' or 'chatgpt'.

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

        if auth_type in ("apikey", "chatgpt"):
            # Import existing credentials if Codex CLI already has them
            existing = get_codex_dir() / "auth.json"
            if existing.exists() and not get_active_profile("codex"):
                shutil.copy2(existing, profile_dir / "auth.json")
                logger.info("Imported existing Codex credentials for %s", label)

        logger.info("Created Codex profile: %s (%s)", label, auth_type)
        return Profile(label=label, auth_type=auth_type, path=profile_dir, meta=meta)

    def remove_profile(self, identifier: str) -> str:
        """Remove a Codex profile."""
        profile = self._resolve_identifier(identifier)

        if profile.is_active:
            raise AuthError(
                f"Cannot remove active profile '{profile.label}'. "
                "Switch to another profile first."
            )

        shutil.rmtree(profile.path)
        logger.info("Removed Codex profile: %s", profile.label)
        return profile.label

    def switch_to(self, identifier: str) -> str:
        """Switch to a Codex profile by index or label."""
        profile = self._resolve_identifier(identifier)

        # Activate based on auth type
        auth_type = profile.meta.get("auth_type", "unknown")
        if auth_type == "apikey":
            auth_file = profile.path / "auth.json"
            if not auth_file.exists():
                raise ProfileCorruptError(
                    f"Missing auth.json in profile '{profile.label}'"
                )
            activate_apikey_profile(profile.path)
        elif auth_type == "chatgpt":
            auth_file = profile.path / "auth.json"
            if not auth_file.exists():
                raise ProfileCorruptError(
                    f"Missing auth.json in profile '{profile.label}'"
                )
            activate_chatgpt_profile(profile.path)
        else:
            raise AuthError(
                f"Unknown auth type '{auth_type}' for profile '{profile.label}'"
            )

        # Update state and meta
        set_active_profile("codex", profile.label)
        profile.meta["last_used"] = datetime.now(timezone.utc).isoformat()
        save_meta(profile.path, profile.meta)

        logger.info("Switched Codex to: %s", profile.label)
        return profile.label

    def switch_next(self) -> str:
        """Rotate to the next Codex profile."""
        profiles = self.list_profiles()
        if len(profiles) < 2:
            raise ProfileNotFoundError(
                f"Need at least 2 profiles to rotate. Currently have {len(profiles)}."
            )

        current = get_active_profile("codex")
        current_idx = 0
        for i, p in enumerate(profiles):
            if p.label == current:
                current_idx = i
                break

        next_idx = (current_idx + 1) % len(profiles)
        return self.switch_to(profiles[next_idx].label)

    def import_credentials(self, path: Path, label: str) -> Profile:
        """Import a credentials file as a new Codex profile.

        Args:
            path: Path to auth.json or a file containing an API key.
            label: Label for the new profile.

        Returns:
            The created Profile.
        """
        if not path.exists():
            raise AuthError(f"File not found: {path}")

        # Detect auth type
        auth_type = self._detect_import_type(path)

        profile = self.add_profile(label, auth_type)

        if auth_type in ("apikey", "chatgpt"):
            shutil.copy2(path, profile.path / "auth.json")
        else:
            # Plain API key text file → create proper auth.json
            api_key = path.read_text(encoding="utf-8").strip()
            auth_data = {
                "OPENAI_API_KEY": api_key,
                "tokens": None,
                "last_refresh": None,
            }
            with (profile.path / "auth.json").open("w", encoding="utf-8") as f:
                json.dump(auth_data, f, indent=2)
                f.write("\n")

        profile.meta["auth_type"] = auth_type
        save_meta(profile.path, profile.meta)
        logger.info("Imported %s credentials as '%s'", auth_type, label)
        return profile

    @staticmethod
    def _detect_import_type(path: Path) -> str:
        """Detect whether a file contains API key or ChatGPT OAuth credentials."""
        try:
            auth_type = detect_auth_type(path)
            return auth_type
        except AuthError:
            pass

        # If it's not valid JSON, treat as plain API key
        content = path.read_text(encoding="utf-8").strip()
        if content.startswith("sk-"):
            return "apikey"

        return "apikey"
