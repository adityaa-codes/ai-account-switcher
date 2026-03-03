"""Utility functions — paths, platform, logging, file locking, symlinks."""

from __future__ import annotations

import fcntl
import logging
import os
import platform
import sys
import tempfile
from contextlib import contextmanager
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterator


def get_config_dir() -> Path:
    """Return the XDG-compliant config directory for cli-switcher."""
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg) if xdg else Path.home() / ".config"
    return base / "cli-switcher"


def get_gemini_dir() -> Path:
    """Return the Gemini CLI config directory (~/.gemini)."""
    return Path.home() / ".gemini"


def get_codex_dir() -> Path:
    """Return the Codex CLI config directory ($CODEX_HOME or ~/.codex)."""
    codex_home = os.environ.get("CODEX_HOME")
    return Path(codex_home) if codex_home else Path.home() / ".codex"


def get_platform_string() -> str:
    """Return platform identifier like 'LINUX_AMD64' or 'LINUX_ARM64'."""
    os_name = sys.platform.upper()
    if os_name.startswith("LINUX"):
        os_name = "LINUX"
    elif os_name == "DARWIN":
        os_name = "MACOS"

    machine = platform.machine().lower()
    arch_map = {
        "x86_64": "AMD64",
        "amd64": "AMD64",
        "aarch64": "ARM64",
        "arm64": "ARM64",
    }
    arch = arch_map.get(machine, machine.upper())
    return f"{os_name}_{arch}"


def setup_logging(level: str = "info") -> logging.Logger:
    """Configure rotating file logger for cli-switcher.

    Args:
        level: Log level string — 'debug', 'info', 'warn', or 'error'.

    Returns:
        The configured root logger for the switcher package.
    """
    log_dir = get_config_dir() / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "switcher.log"

    logger = logging.getLogger("switcher")
    if logger.handlers:
        return logger

    numeric_level = getattr(logging, level.upper(), logging.INFO)
    logger.setLevel(numeric_level)

    handler = RotatingFileHandler(
        log_file, maxBytes=1_000_000, backupCount=3, encoding="utf-8"
    )
    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    return logger


@contextmanager
def file_lock(path: Path) -> Iterator[None]:
    """Exclusive file lock using fcntl.flock.

    Args:
        path: Path to the lock file (created if it doesn't exist).
    """
    lock_path = path.with_suffix(path.suffix + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fd = lock_path.open("w")
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        fd.close()


def atomic_symlink(source: Path, target: Path) -> None:
    """Create a symlink atomically via temp link + os.replace.

    Args:
        source: The file the symlink points to (must exist).
        target: The symlink path to create/replace.
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(
        dir=target.parent, prefix=f".{target.name}.", suffix=".tmp"
    )
    os.close(fd)
    tmp = Path(tmp_path)
    try:
        tmp.unlink()
        tmp.symlink_to(source.resolve())
        os.replace(tmp, target)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def ensure_dirs() -> None:
    """Create all required directories on first run."""
    config = get_config_dir()
    dirs = [
        config,
        config / "profiles" / "gemini",
        config / "profiles" / "codex",
        config / "hooks",
        config / "cache",
        config / "logs",
    ]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)
