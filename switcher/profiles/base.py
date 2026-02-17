"""Abstract profile manager and shared data types."""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path


@dataclass(slots=True)
class Profile:
    """Represents a single CLI auth profile."""

    label: str
    auth_type: str  # "oauth", "apikey", "chatgpt"
    path: Path
    is_active: bool = False
    meta: dict[str, Any] = field(default_factory=dict)


def load_meta(profile_dir: Path) -> dict[str, Any]:
    """Read meta.json from a profile directory.

    Args:
        profile_dir: Path to the profile directory.

    Returns:
        Parsed meta dict, or defaults if file is missing/corrupt.
    """
    meta_path = profile_dir / "meta.json"
    if not meta_path.exists():
        return _default_meta(profile_dir.name)
    try:
        with meta_path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return _default_meta(profile_dir.name)


def save_meta(profile_dir: Path, meta: dict[str, Any]) -> None:
    """Write meta.json to a profile directory.

    Args:
        profile_dir: Path to the profile directory.
        meta: Meta dict to persist.
    """
    meta_path = profile_dir / "meta.json"
    profile_dir.mkdir(parents=True, exist_ok=True)
    with meta_path.open("w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)
        f.write("\n")


def _default_meta(label: str) -> dict[str, Any]:
    """Return a default meta dict for a new profile."""
    return {
        "label": label,
        "auth_type": "unknown",
        "added_at": datetime.now(timezone.utc).isoformat(),
        "last_used": None,
        "last_health_check": None,
        "health_status": "unknown",
        "health_detail": None,
        "notes": "",
    }


class ProfileManager(ABC):
    """Abstract base for CLI-specific profile managers."""

    def __init__(self, cli_name: str, profiles_dir: Path, target_dir: Path) -> None:
        self.cli_name = cli_name
        self.profiles_dir = profiles_dir
        self.target_dir = target_dir

    @abstractmethod
    def list_profiles(self) -> list[Profile]:
        """List all profiles for this CLI."""

    @abstractmethod
    def get_profile(self, identifier: str) -> Profile:
        """Get a profile by index (1-based) or label.

        Args:
            identifier: 1-based index string or profile label.

        Raises:
            ProfileNotFoundError: If no matching profile is found.
        """

    @abstractmethod
    def add_profile(self, label: str, auth_type: str) -> Profile:
        """Add a new profile.

        Args:
            label: Profile label (email or descriptive name).
            auth_type: One of 'oauth', 'apikey', 'chatgpt'.

        Returns:
            The newly created Profile.
        """

    @abstractmethod
    def remove_profile(self, identifier: str) -> str:
        """Remove a profile by index or label.

        Args:
            identifier: 1-based index string or profile label.

        Returns:
            The label of the removed profile.
        """

    @abstractmethod
    def switch_to(self, identifier: str) -> str:
        """Switch to a profile by index or label.

        Args:
            identifier: 1-based index string or profile label.

        Returns:
            The label of the newly active profile.
        """

    @abstractmethod
    def switch_next(self) -> str:
        """Rotate to the next profile.

        Returns:
            The label of the newly active profile.
        """

    @abstractmethod
    def import_credentials(self, path: Path, label: str) -> Profile:
        """Import a credentials file as a new profile.

        Args:
            path: Path to the credentials file.
            label: Label for the new profile.

        Returns:
            The newly created Profile.
        """

    def _resolve_identifier(self, identifier: str) -> Profile:
        """Resolve an index or label string to a Profile.

        Args:
            identifier: 1-based index string or profile label.

        Raises:
            ProfileNotFoundError: If not found.
        """
        from switcher.errors import ProfileNotFoundError

        profiles = self.list_profiles()
        if not profiles:
            raise ProfileNotFoundError(
                f"No {self.cli_name} profiles configured. "
                f"Run: switcher {self.cli_name} add"
            )

        # Try as 1-based index
        if identifier.isdigit():
            idx = int(identifier) - 1
            if 0 <= idx < len(profiles):
                return profiles[idx]
            raise ProfileNotFoundError(
                f"Profile index {identifier} out of range (1-{len(profiles)})"
            )

        # Try as label (case-insensitive)
        for p in profiles:
            if p.label.lower() == identifier.lower():
                return p

        raise ProfileNotFoundError(
            f"No {self.cli_name} profile matching '{identifier}'"
        )
