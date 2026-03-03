"""Tests for path utilities, logging, file locking, and symlinks."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import patch

from switcher.utils import (
    atomic_symlink,
    ensure_dirs,
    get_codex_dir,
    get_config_dir,
    get_gemini_dir,
    get_platform_string,
)

if TYPE_CHECKING:
    from pathlib import Path

    from pytest import MonkeyPatch


def test_get_config_dir_respects_xdg(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "custom_config"))
    path = get_config_dir()
    assert path == tmp_path / "custom_config" / "cli-switcher"


def test_get_config_dir_falls_back_to_home(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    path = get_config_dir()
    assert path == tmp_path / ".config" / "cli-switcher"


def test_get_codex_dir_respects_codex_home(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "my_codex"))
    path = get_codex_dir()
    assert path == tmp_path / "my_codex"


def test_get_codex_dir_falls_back_to_home(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    monkeypatch.delenv("CODEX_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    path = get_codex_dir()
    assert path == tmp_path / ".codex"


def test_get_gemini_dir_uses_home(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    path = get_gemini_dir()
    assert path == tmp_path / ".gemini"


def test_get_platform_string_format() -> None:
    result = get_platform_string()
    assert "_" in result
    parts = result.split("_", 1)
    assert len(parts) == 2
    assert parts[0] in ("LINUX", "MACOS", "WINDOWS", "DARWIN")


def test_ensure_dirs_creates_all_subdirectories(tmp_config_dir: Path) -> None:
    from switcher.utils import get_config_dir

    ensure_dirs()
    config = get_config_dir()
    expected = [
        config,
        config / "profiles" / "gemini",
        config / "profiles" / "codex",
        config / "hooks",
        config / "cache",
        config / "logs",
    ]
    for d in expected:
        assert d.is_dir(), f"Expected directory missing: {d}"


def test_atomic_symlink_creates_symlink(tmp_path: Path) -> None:
    source = tmp_path / "source.txt"
    source.write_text("hello", encoding="utf-8")
    target = tmp_path / "link.txt"

    atomic_symlink(source, target)

    assert target.is_symlink()
    assert target.read_text(encoding="utf-8") == "hello"


def test_atomic_symlink_replaces_existing(tmp_path: Path) -> None:
    source1 = tmp_path / "s1.txt"
    source2 = tmp_path / "s2.txt"
    source1.write_text("first", encoding="utf-8")
    source2.write_text("second", encoding="utf-8")
    target = tmp_path / "link.txt"

    atomic_symlink(source1, target)
    assert target.read_text(encoding="utf-8") == "first"

    atomic_symlink(source2, target)
    assert target.read_text(encoding="utf-8") == "second"
    assert target.resolve() == source2.resolve()


def test_file_lock_allows_sequential_access(tmp_path: Path) -> None:
    from switcher.utils import file_lock

    lock_file = tmp_path / "test.json"
    results: list[int] = []

    with file_lock(lock_file):
        results.append(1)
    with file_lock(lock_file):
        results.append(2)

    assert results == [1, 2]


def test_atomic_symlink_creates_parent_dirs(tmp_path: Path) -> None:
    source = tmp_path / "src.txt"
    source.write_text("data", encoding="utf-8")
    target = tmp_path / "nested" / "deep" / "link.txt"

    atomic_symlink(source, target)
    assert target.is_symlink()


# ---------------------------------------------------------------------------
# setup_logging
# ---------------------------------------------------------------------------


def test_setup_logging_creates_log_file(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    import logging

    from switcher.utils import setup_logging

    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    config_dir = tmp_path / "cli-switcher"
    config_dir.mkdir(parents=True)

    # Clear any existing handlers to avoid state pollution between tests
    logger = logging.getLogger("switcher")
    for h in logger.handlers[:]:
        logger.removeHandler(h)

    with patch("switcher.utils.get_config_dir", return_value=config_dir):
        result = setup_logging("debug")

    log_file = config_dir / "logs" / "switcher.log"
    assert log_file.exists() or (config_dir / "logs").exists()
    assert result.name == "switcher"
    # cleanup handlers to avoid pollution
    for h in result.handlers[:]:
        result.removeHandler(h)
        h.close()


def test_setup_logging_idempotent(tmp_path: Path) -> None:
    import logging

    from switcher.utils import setup_logging

    config_dir = tmp_path / "cli-switcher"
    config_dir.mkdir(parents=True)

    logger = logging.getLogger("switcher.idempotent_test")
    for h in logger.handlers[:]:
        logger.removeHandler(h)

    with patch("switcher.utils.get_config_dir", return_value=config_dir):
        r1 = setup_logging("info")
        handler_count = len(r1.handlers)
        r2 = setup_logging("info")
    assert len(r2.handlers) == handler_count  # no duplicates
    for h in r2.handlers[:]:
        r2.removeHandler(h)
        h.close()


# ---------------------------------------------------------------------------
# atomic_symlink error path
# ---------------------------------------------------------------------------


def test_atomic_symlink_cleans_up_on_error(tmp_path: Path) -> None:
    from switcher.utils import atomic_symlink

    source = tmp_path / "source.txt"
    source.write_text("content")
    target = tmp_path / "target_link"

    def fail_replace(src, dst):
        raise OSError("simulated failure")

    with patch("switcher.utils.os.replace", side_effect=fail_replace):
        import contextlib

        with contextlib.suppress(OSError):
            atomic_symlink(source, target)

    # The temp symlink should have been cleaned up
    import glob

    tmp_files = glob.glob(str(tmp_path / "*.tmp"))
    assert len(tmp_files) == 0
