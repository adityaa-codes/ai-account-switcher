"""Codex sandbox policy isolation — snapshot and restore per-profile policies.

Codex CLI 0.113+ introduced permission profiles with filesystem and network
sandbox splits stored in ``~/.codex/policy.toml`` (or equivalent).  This
module snapshots the file when switching away from a profile and restores it
when switching to a profile.
"""

from __future__ import annotations

import logging
import shutil
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

logger = logging.getLogger("switcher.auth.codex_sandbox")

# Candidate filenames for the Codex sandbox policy, newest → oldest.
_POLICY_CANDIDATES: list[str] = [
    "policy.toml",
    "sandbox.toml",
    "permissions.toml",
]
_SNAPSHOT_FILENAME = "policy.toml"


def get_codex_policy_path(codex_dir: Path) -> Path | None:
    """Return the path to the active Codex sandbox policy file, or None.

    Args:
        codex_dir: Root Codex directory (``~/.codex``).

    Returns:
        Path to the policy file if found, otherwise ``None``.
    """
    for name in _POLICY_CANDIDATES:
        p = codex_dir / name
        if p.exists():
            return p
    return None


def snapshot_policy(codex_dir: Path, profile_dir: Path) -> bool:
    """Copy the active Codex sandbox policy into a profile directory.

    Called when switching *away* from a profile.

    Args:
        codex_dir: Root Codex directory (``~/.codex``).
        profile_dir: Profile directory to write the snapshot into.

    Returns:
        ``True`` if a policy was found and snapshotted, ``False`` otherwise.
    """
    src = get_codex_policy_path(codex_dir)
    if src is None:
        logger.debug("No Codex policy file found; skipping snapshot.")
        return False

    dest = profile_dir / _SNAPSHOT_FILENAME
    shutil.copy2(src, dest)
    logger.info("Snapshotted Codex policy %s → %s", src.name, dest)
    return True


def restore_policy(profile_dir: Path, codex_dir: Path) -> bool:
    """Restore a Codex sandbox policy from a profile snapshot.

    If no snapshot exists in the profile directory the live policy is left
    untouched.

    Args:
        profile_dir: Profile directory containing the snapshot.
        codex_dir: Root Codex directory (``~/.codex``).

    Returns:
        ``True`` if a snapshot was restored, ``False`` otherwise.
    """
    snap = profile_dir / _SNAPSHOT_FILENAME
    if not snap.exists():
        logger.debug(
            "No policy snapshot in %s; leaving live policy untouched.", profile_dir
        )
        return False

    # Use the first candidate as the canonical live path.
    live = codex_dir / _POLICY_CANDIDATES[0]
    shutil.copy2(snap, live)
    logger.info("Restored Codex policy → %s", live)
    return True
