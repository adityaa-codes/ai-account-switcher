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

APP_CONFIG_DIR = "ai-account-switcher"
LEGACY_APP_CONFIG_DIR = "cli-switcher"


def get_config_dir() -> Path:
    """Return the XDG-compliant config directory for ai-account-switcher.

    Existing installs under the legacy ``cli-switcher`` path are migrated to the
    canonical directory when possible. If migration fails, keep using the legacy
    directory rather than risking data loss.
    """
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg) if xdg else Path.home() / ".config"
    config_dir = base / APP_CONFIG_DIR
    legacy_dir = base / LEGACY_APP_CONFIG_DIR

    if config_dir.exists() or not legacy_dir.exists():
        return config_dir

    try:
        legacy_dir.rename(config_dir)
    except OSError:
        return legacy_dir

    return config_dir


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
    """Configure rotating file loggers for ai-account-switcher.

    Creates three log files under ``~/.config/ai-account-switcher/logs/``:

    * ``switcher.log``  — all messages at the configured level.
    * ``errors.log``    — ERROR and above only, for quick error triage.
    * ``commands.log``  — one line per CLI invocation with duration and status.

    Args:
        level: Log level string — 'debug', 'info', 'warn', or 'error'.

    Returns:
        The configured root logger for the switcher package.
    """
    log_dir = get_config_dir() / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger("switcher")
    if logger.handlers:
        return logger

    numeric_level = getattr(logging, level.upper(), logging.INFO)
    logger.setLevel(numeric_level)

    detail_fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )

    # General log — all messages at the configured level.
    general_handler = RotatingFileHandler(
        log_dir / "switcher.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8"
    )
    general_handler.setFormatter(detail_fmt)
    logger.addHandler(general_handler)

    # Error log — ERROR and above only.
    error_handler = RotatingFileHandler(
        log_dir / "errors.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8"
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(detail_fmt)
    logger.addHandler(error_handler)

    # Command log — separate non-propagating logger so command entries don't
    # bleed into switcher.log.
    cmd_logger = logging.getLogger("switcher.commands")
    if not cmd_logger.handlers:
        cmd_logger.propagate = False
        cmd_logger.setLevel(logging.INFO)
        cmd_handler = RotatingFileHandler(
            log_dir / "commands.log",
            maxBytes=1_000_000,
            backupCount=3,
            encoding="utf-8",
        )
        cmd_handler.setFormatter(
            logging.Formatter("%(asctime)s %(message)s", datefmt="%Y-%m-%dT%H:%M:%S")
        )
        cmd_logger.addHandler(cmd_handler)

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
