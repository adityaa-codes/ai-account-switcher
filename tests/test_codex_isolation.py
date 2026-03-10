"""Tests for Codex memory, plugin, and sandbox isolation (Phase 4: E, F, J)."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


# ---------------------------------------------------------------------------
# E-1/E-2: codex_memory
# ---------------------------------------------------------------------------


class TestCodexMemory:
    def test_get_memory_path_sqlite_db(self, tmp_path: Path) -> None:
        """E-1: detects SQLite DB at db/memories.db."""
        from switcher.auth.codex_memory import get_codex_memory_path

        db = tmp_path / "db" / "memories.db"
        db.parent.mkdir()
        db.write_bytes(b"SQLite format 3")
        result = get_codex_memory_path(tmp_path)
        assert result == db

    def test_get_memory_path_flat_dir(self, tmp_path: Path) -> None:
        """E-1: falls back to memories/ directory for older Codex."""
        from switcher.auth.codex_memory import get_codex_memory_path

        mem_dir = tmp_path / "memories"
        mem_dir.mkdir()
        result = get_codex_memory_path(tmp_path)
        assert result == mem_dir

    def test_get_memory_path_returns_none_when_absent(self, tmp_path: Path) -> None:
        """E-1: returns None when no memory store found."""
        from switcher.auth.codex_memory import get_codex_memory_path

        assert get_codex_memory_path(tmp_path) is None

    def test_snapshot_memory_sqlite(self, tmp_path: Path) -> None:
        """E-2: snapshot_memory copies SQLite DB to profile dir."""
        from switcher.auth.codex_memory import snapshot_memory

        codex_dir = tmp_path / "codex"
        codex_dir.mkdir()
        db = codex_dir / "memories.db"
        db.write_bytes(b"db content")

        profile_dir = tmp_path / "profile"
        profile_dir.mkdir()

        result = snapshot_memory(codex_dir, profile_dir)
        assert result is True
        assert (profile_dir / "memories.db").read_bytes() == b"db content"

    def test_snapshot_memory_no_store_returns_false(self, tmp_path: Path) -> None:
        """E-2: snapshot_memory returns False when no memory store found."""
        from switcher.auth.codex_memory import snapshot_memory

        codex_dir = tmp_path / "codex"
        codex_dir.mkdir()
        profile_dir = tmp_path / "profile"
        profile_dir.mkdir()

        assert snapshot_memory(codex_dir, profile_dir) is False

    def test_restore_memory_sqlite(self, tmp_path: Path) -> None:
        """E-2: restore_memory copies snapshot DB to live Codex dir."""
        from switcher.auth.codex_memory import restore_memory

        profile_dir = tmp_path / "profile"
        profile_dir.mkdir()
        snap = profile_dir / "memories.db"
        snap.write_bytes(b"snap content")

        codex_dir = tmp_path / "codex"
        codex_dir.mkdir()

        result = restore_memory(profile_dir, codex_dir)
        assert result is True
        # Should have written to first candidate path
        assert (codex_dir / "db" / "memories.db").read_bytes() == b"snap content"

    def test_restore_memory_no_snapshot_returns_false(self, tmp_path: Path) -> None:
        """E-2: restore_memory returns False when no snapshot exists."""
        from switcher.auth.codex_memory import restore_memory

        profile_dir = tmp_path / "profile"
        profile_dir.mkdir()
        codex_dir = tmp_path / "codex"
        codex_dir.mkdir()

        assert restore_memory(profile_dir, codex_dir) is False


# ---------------------------------------------------------------------------
# F-1/F-2/F-3: codex_plugins
# ---------------------------------------------------------------------------


class TestCodexPlugins:
    def test_list_installed_plugins_empty(self, tmp_path: Path) -> None:
        """F-1: returns empty list when plugins dir absent."""
        from switcher.auth.codex_plugins import list_installed_plugins

        assert list_installed_plugins(tmp_path) == []

    def test_list_installed_plugins(self, tmp_path: Path) -> None:
        """F-1: returns sorted plugin names from plugins/ subdirectory."""
        from switcher.auth.codex_plugins import list_installed_plugins

        plugins_dir = tmp_path / "plugins"
        plugins_dir.mkdir()
        (plugins_dir / "web-search").mkdir()
        (plugins_dir / "git-helper").mkdir()

        result = list_installed_plugins(tmp_path)
        assert result == ["git-helper", "web-search"]

    def test_snapshot_plugins_writes_json(self, tmp_path: Path) -> None:
        """F-2: snapshot_plugins writes plugins.json to profile dir."""
        from switcher.auth.codex_plugins import snapshot_plugins

        codex_dir = tmp_path / "codex"
        (codex_dir / "plugins" / "my-plugin").mkdir(parents=True)
        profile_dir = tmp_path / "profile"
        profile_dir.mkdir()

        snapshot_plugins(codex_dir, profile_dir)

        data = json.loads((profile_dir / "plugins.json").read_text())
        assert data == ["my-plugin"]

    def test_warn_plugin_divergence_missing_plugin(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """F-3: warns when expected plugin is not installed."""
        from switcher.auth.codex_plugins import warn_plugin_divergence

        profile_dir = tmp_path / "profile"
        profile_dir.mkdir()
        (profile_dir / "plugins.json").write_text(
            json.dumps(["web-search"]), encoding="utf-8"
        )

        codex_dir = tmp_path / "codex"
        codex_dir.mkdir()  # no plugins installed

        with caplog.at_level("WARNING", logger="switcher.auth.codex_plugins"):
            missing = warn_plugin_divergence(profile_dir, codex_dir)

        assert "web-search" in missing
        assert any("web-search" in r.message for r in caplog.records)

    def test_warn_plugin_divergence_no_missing(self, tmp_path: Path) -> None:
        """F-3: returns empty list when all expected plugins are installed."""
        from switcher.auth.codex_plugins import warn_plugin_divergence

        profile_dir = tmp_path / "profile"
        profile_dir.mkdir()
        (profile_dir / "plugins.json").write_text(
            json.dumps(["web-search"]), encoding="utf-8"
        )

        codex_dir = tmp_path / "codex"
        (codex_dir / "plugins" / "web-search").mkdir(parents=True)

        assert warn_plugin_divergence(profile_dir, codex_dir) == []


# ---------------------------------------------------------------------------
# J-1/J-2: codex_sandbox
# ---------------------------------------------------------------------------


class TestCodexSandbox:
    def test_get_policy_path_returns_none_when_absent(self, tmp_path: Path) -> None:
        """J-1: returns None when no policy file found."""
        from switcher.auth.codex_sandbox import get_codex_policy_path

        assert get_codex_policy_path(tmp_path) is None

    def test_get_policy_path_finds_policy_toml(self, tmp_path: Path) -> None:
        """J-1: finds policy.toml in Codex dir."""
        from switcher.auth.codex_sandbox import get_codex_policy_path

        pol = tmp_path / "policy.toml"
        pol.write_text("[policy]\n")
        assert get_codex_policy_path(tmp_path) == pol

    def test_snapshot_policy_copies_file(self, tmp_path: Path) -> None:
        """J-1: snapshot_policy copies the policy file to the profile dir."""
        from switcher.auth.codex_sandbox import snapshot_policy

        codex_dir = tmp_path / "codex"
        codex_dir.mkdir()
        pol = codex_dir / "policy.toml"
        pol.write_text("[sandbox]\nnetwork = false\n")

        profile_dir = tmp_path / "profile"
        profile_dir.mkdir()

        assert snapshot_policy(codex_dir, profile_dir) is True
        snap_content = (profile_dir / "policy.toml").read_text()
        assert snap_content == "[sandbox]\nnetwork = false\n"

    def test_snapshot_policy_returns_false_when_absent(self, tmp_path: Path) -> None:
        """J-1: returns False when no policy file found."""
        from switcher.auth.codex_sandbox import snapshot_policy

        codex_dir = tmp_path / "codex"
        codex_dir.mkdir()
        profile_dir = tmp_path / "profile"
        profile_dir.mkdir()

        assert snapshot_policy(codex_dir, profile_dir) is False

    def test_restore_policy_copies_snapshot(self, tmp_path: Path) -> None:
        """J-2: restore_policy copies snapshot to live Codex dir."""
        from switcher.auth.codex_sandbox import restore_policy

        profile_dir = tmp_path / "profile"
        profile_dir.mkdir()
        (profile_dir / "policy.toml").write_text("[sandbox]\n")

        codex_dir = tmp_path / "codex"
        codex_dir.mkdir()

        assert restore_policy(profile_dir, codex_dir) is True
        assert (codex_dir / "policy.toml").read_text() == "[sandbox]\n"

    def test_restore_policy_no_snapshot_returns_false(self, tmp_path: Path) -> None:
        """J-2: returns False when no snapshot exists."""
        from switcher.auth.codex_sandbox import restore_policy

        profile_dir = tmp_path / "profile"
        profile_dir.mkdir()
        codex_dir = tmp_path / "codex"
        codex_dir.mkdir()

        assert restore_policy(profile_dir, codex_dir) is False
