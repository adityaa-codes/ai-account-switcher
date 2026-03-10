"""Codex plugin state isolation — snapshot and restore per-profile plugin lists.

Codex CLI 0.113+ ships a plugin marketplace.  Plugins are installed globally
under ``~/.codex/plugins/``.  This module snapshots the installed plugin list
when switching away from a profile and warns (but does not auto-install) when
the active plugin list diverges from the incoming profile's expected list.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

logger = logging.getLogger("switcher.auth.codex_plugins")

# Where Codex stores installed plugins.
_PLUGINS_SUBDIR = "plugins"
_SNAPSHOT_FILENAME = "plugins.json"


def list_installed_plugins(codex_dir: Path) -> list[str]:
    """Return the names of currently installed Codex plugins.

    Reads the directory listing of ``~/.codex/plugins/``.  Each subdirectory
    is treated as an installed plugin.

    Args:
        codex_dir: Root Codex directory (``~/.codex``).

    Returns:
        Sorted list of plugin names, or empty list if none installed.
    """
    plugins_dir = codex_dir / _PLUGINS_SUBDIR
    if not plugins_dir.is_dir():
        return []
    return sorted(
        entry.name for entry in plugins_dir.iterdir() if entry.is_dir()
    )


def snapshot_plugins(codex_dir: Path, profile_dir: Path) -> bool:
    """Save the current Codex plugin list to a profile directory.

    Called when switching *away* from a profile.

    Args:
        codex_dir: Root Codex directory (``~/.codex``).
        profile_dir: Profile directory to write the snapshot into.

    Returns:
        ``True`` if a snapshot was written, ``False`` if plugins dir absent.
    """
    plugins = list_installed_plugins(codex_dir)
    dest = profile_dir / _SNAPSHOT_FILENAME
    dest.write_text(json.dumps(plugins, indent=2) + "\n", encoding="utf-8")
    logger.info(
        "Snapshotted %d Codex plugin(s) for profile %s",
        len(plugins),
        profile_dir.name,
    )
    return True


def warn_plugin_divergence(
    profile_dir: Path, codex_dir: Path
) -> list[str]:
    """Compare the profile's expected plugins with what is currently installed.

    Logs a warning for any plugins that are expected but not installed, and
    returns the list of missing plugins.  Does NOT auto-install anything.

    Args:
        profile_dir: Profile directory containing the snapshot.
        codex_dir: Root Codex directory (``~/.codex``).

    Returns:
        List of plugin names that are in the snapshot but not installed.
    """
    snap_path = profile_dir / _SNAPSHOT_FILENAME
    if not snap_path.exists():
        return []

    try:
        expected: list[str] = json.loads(snap_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        logger.warning(
            "Could not read plugin snapshot from %s; skipping divergence check.",
            snap_path,
        )
        return []

    installed = set(list_installed_plugins(codex_dir))
    missing = [p for p in expected if p not in installed]

    if missing:
        logger.warning(
            "Codex profile '%s' expects plugin(s) not currently installed: %s. "
            "Install manually with 'codex plugin install <name>'.",
            profile_dir.name,
            ", ".join(missing),
        )

    return missing
