"""Codex memory isolation — snapshot and restore per-profile memory stores.

Codex CLI 0.113+ stores AI memory in a SQLite database (``~/.codex/db/``).
Older versions use flat files under ``~/.codex/memories/``.  This module
provides a unified interface to snapshot memory when switching away from a
profile and to restore it when switching to a profile.
"""

from __future__ import annotations

import logging
import shutil
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

logger = logging.getLogger("switcher.auth.codex_memory")

# Known paths for Codex memory store (newest → oldest).
_DB_CANDIDATES: list[str] = [
    "db/memories.db",
    "memories.db",
]
_FLAT_DIR = "memories"


def get_codex_memory_path(codex_dir: Path) -> Path | None:
    """Return the active Codex memory store path, or None if not found.

    Tries SQLite file locations first (Codex 0.113+), then falls back
    to the flat-file memories directory.

    Args:
        codex_dir: Root Codex directory (typically ``~/.codex``).

    Returns:
        Path to the SQLite file or memories directory, or ``None``.
    """
    for rel in _DB_CANDIDATES:
        p = codex_dir / rel
        if p.exists():
            return p
    flat = codex_dir / _FLAT_DIR
    if flat.is_dir():
        return flat
    return None


def snapshot_memory(codex_dir: Path, profile_dir: Path) -> bool:
    """Copy the active Codex memory store into a profile directory.

    Used when switching *away* from a profile so its memories are preserved.

    Args:
        codex_dir: Root Codex directory (``~/.codex``).
        profile_dir: Profile directory to snapshot into.

    Returns:
        ``True`` if a snapshot was taken, ``False`` if nothing to snapshot.
    """
    src = get_codex_memory_path(codex_dir)
    if src is None:
        logger.debug("No Codex memory store found; skipping snapshot.")
        return False

    if src.is_file():
        dest = profile_dir / "memories.db"
        shutil.copy2(src, dest)
        logger.info("Snapshotted Codex memory DB → %s", dest)
    else:
        dest = profile_dir / "memories"
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(src, dest)
        logger.info("Snapshotted Codex memory dir → %s", dest)
    return True


def restore_memory(profile_dir: Path, codex_dir: Path) -> bool:
    """Restore a previously snapshotted Codex memory store.

    Used when switching *to* a profile.  If no snapshot exists the live
    memory store is left untouched.

    Args:
        profile_dir: Profile directory containing the snapshot.
        codex_dir: Root Codex directory (``~/.codex``).

    Returns:
        ``True`` if a snapshot was restored, ``False`` otherwise.
    """
    db_snap = profile_dir / "memories.db"
    dir_snap = profile_dir / "memories"

    if db_snap.exists():
        # Determine canonical live path (use first matching candidate).
        for rel in _DB_CANDIDATES:
            live = codex_dir / rel
            live.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(db_snap, live)
            logger.info("Restored Codex memory DB → %s", live)
            return True

    if dir_snap.is_dir():
        live_dir = codex_dir / _FLAT_DIR
        if live_dir.exists():
            shutil.rmtree(live_dir)
        shutil.copytree(dir_snap, live_dir)
        logger.info("Restored Codex memory dir → %s", live_dir)
        return True

    logger.debug("No memory snapshot in %s; leaving live store untouched.", profile_dir)
    return False
