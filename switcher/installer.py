"""Installer for shell integration, Gemini hooks, and bin symlink."""

from __future__ import annotations

import json
import os
import shutil
from typing import TYPE_CHECKING

from switcher.ui import print_info, print_success, print_warning
from switcher.utils import get_config_dir, get_gemini_dir

if TYPE_CHECKING:
    from pathlib import Path

# Marker comments for RC file injection
_MARKER_START = "# >>> cli-switcher >>>"
_MARKER_END = "# <<< cli-switcher <<<"

# Hook names used in settings.json
_HOOK_AFTER = "switcher-auto-rotate"
_HOOK_BEFORE = "switcher-pre-check"


# ---------------------------------------------------------------------------
# Shell detection
# ---------------------------------------------------------------------------


def detect_shell() -> str:
    """Detect the current user shell from $SHELL."""
    shell = os.environ.get("SHELL", "/bin/bash")
    basename = os.path.basename(shell)
    if "zsh" in basename:
        return "zsh"
    if "fish" in basename:
        return "fish"
    return "bash"


def get_rc_file(shell: str | None = None) -> Path:
    """Return the RC file path for the given shell."""
    from pathlib import Path

    shell = shell or detect_shell()
    home = Path.home()
    rc_map = {
        "bash": home / ".bashrc",
        "zsh": home / ".zshrc",
        "fish": home / ".config" / "fish" / "config.fish",
    }
    return rc_map.get(shell, home / ".bashrc")


# ---------------------------------------------------------------------------
# Shell RC snippet
# ---------------------------------------------------------------------------


def generate_shell_snippet() -> str:
    """Generate the shell integration block."""
    env_sh = get_config_dir() / "env.sh"
    return f"""{_MARKER_START}
# CLI Switcher — shell integration (managed by 'switcher install')
[ -f "{env_sh}" ] && source "{env_sh}"

alias sw='switcher'

gemini() {{
    [ -f "{env_sh}" ] && source "{env_sh}"
    command gemini "$@"
}}

codex() {{
    [ -f "{env_sh}" ] && source "{env_sh}"
    command codex "$@"
}}
{_MARKER_END}"""


def inject_into_rc(rc_path: Path) -> bool:
    """Append shell snippet to RC file if not already present.

    Returns True if snippet was injected, False if already present.
    """
    rc_path.parent.mkdir(parents=True, exist_ok=True)

    if rc_path.exists():
        content = rc_path.read_text()
        if _MARKER_START in content:
            return False
    else:
        content = ""

    snippet = generate_shell_snippet()
    with rc_path.open("a") as f:
        f.write(f"\n{snippet}\n")
    return True


def remove_from_rc(rc_path: Path) -> bool:
    """Remove shell snippet between marker comments.

    Returns True if snippet was removed, False if not found.
    """
    if not rc_path.exists():
        return False

    lines = rc_path.read_text().splitlines(keepends=True)
    new_lines: list[str] = []
    inside = False
    removed = False

    for line in lines:
        if _MARKER_START in line:
            inside = True
            removed = True
            continue
        if _MARKER_END in line:
            inside = False
            continue
        if not inside:
            new_lines.append(line)

    if removed:
        rc_path.write_text("".join(new_lines))
    return removed


# ---------------------------------------------------------------------------
# Gemini hooks in settings.json
# ---------------------------------------------------------------------------


def _hook_script_path(name: str) -> str:
    """Return the installed path for a hook script."""
    return str(get_config_dir() / "hooks" / name)


def install_gemini_hooks(settings_path: Path | None = None) -> bool:
    """Merge auto-rotation hooks into Gemini settings.json.

    Returns True if hooks were added, False if already present.
    """
    if settings_path is None:
        settings_path = get_gemini_dir() / "settings.json"

    settings_path.parent.mkdir(parents=True, exist_ok=True)

    settings: dict = {}  # type: ignore[type-arg]
    if settings_path.exists():
        try:
            settings = json.loads(settings_path.read_text())
        except json.JSONDecodeError:
            settings = {}

    hooks = settings.setdefault("hooks", {})
    changed = False

    # AfterAgent hook
    after_list = hooks.setdefault("AfterAgent", [])
    if not any(
        h.get("name") == _HOOK_AFTER
        for group in after_list
        for h in group.get("hooks", [])
    ):
        after_list.append(
            {
                "matcher": "*",
                "hooks": [
                    {
                        "name": _HOOK_AFTER,
                        "type": "command",
                        "command": (
                            f"python3 {_hook_script_path('gemini_after_agent.py')}"
                        ),
                        "timeout": 10000,
                        "description": "Auto-switch on quota exhaustion",
                    }
                ],
            }
        )
        changed = True

    # BeforeAgent hook
    before_list = hooks.setdefault("BeforeAgent", [])
    if not any(
        h.get("name") == _HOOK_BEFORE
        for group in before_list
        for h in group.get("hooks", [])
    ):
        before_list.append(
            {
                "matcher": "*",
                "hooks": [
                    {
                        "name": _HOOK_BEFORE,
                        "type": "command",
                        "command": (
                            f"python3 {_hook_script_path('gemini_before_agent.py')}"
                        ),
                        "timeout": 10000,
                        "description": "Pre-check quota before request",
                    }
                ],
            }
        )
        changed = True

    if changed:
        settings_path.write_text(json.dumps(settings, indent=2) + "\n")
    return changed


def remove_gemini_hooks(settings_path: Path | None = None) -> bool:
    """Remove switcher hooks from Gemini settings.json.

    Returns True if hooks were removed, False if not found.
    """
    if settings_path is None:
        settings_path = get_gemini_dir() / "settings.json"

    if not settings_path.exists():
        return False

    try:
        settings = json.loads(settings_path.read_text())
    except json.JSONDecodeError:
        return False

    hooks = settings.get("hooks", {})
    changed = False

    for hook_type in ("AfterAgent", "BeforeAgent"):
        groups = hooks.get(hook_type, [])
        new_groups = []
        for group in groups:
            filtered = [
                h
                for h in group.get("hooks", [])
                if h.get("name") not in (_HOOK_AFTER, _HOOK_BEFORE)
            ]
            if filtered:
                group["hooks"] = filtered
                new_groups.append(group)
            elif group.get("hooks"):
                changed = True
        if len(new_groups) != len(groups):
            changed = True
        hooks[hook_type] = new_groups

    if changed:
        settings_path.write_text(json.dumps(settings, indent=2) + "\n")
    return changed


# ---------------------------------------------------------------------------
# Slash command (Gemini /change)
# ---------------------------------------------------------------------------


def install_slash_command(commands_dir: Path | None = None) -> bool:
    """Write the /change slash command TOML file for Gemini CLI."""
    if commands_dir is None:
        commands_dir = get_gemini_dir() / "commands"

    commands_dir.mkdir(parents=True, exist_ok=True)
    toml_path = commands_dir / "change.toml"

    if toml_path.exists():
        return False

    toml_path.write_text(
        "[command]\n"
        'name = "change"\n'
        'description = "Switch to next Gemini account"\n'
        'command = "switcher gemini next"\n'
    )
    return True


def remove_slash_command(commands_dir: Path | None = None) -> bool:
    """Remove the /change slash command."""
    if commands_dir is None:
        commands_dir = get_gemini_dir() / "commands"

    toml_path = commands_dir / "change.toml"
    if toml_path.exists():
        toml_path.unlink()
        return True
    return False


# ---------------------------------------------------------------------------
# env.sh generation
# ---------------------------------------------------------------------------


def generate_env_sh() -> None:
    """Write env.sh with active API key profile env vars."""
    from switcher.state import load_state

    env_sh = get_config_dir() / "env.sh"
    env_sh.parent.mkdir(parents=True, exist_ok=True)

    lines = [
        "# Auto-generated by cli-switcher — do not edit manually",
        "# Sourced by shell wrappers for env-var-based auth",
    ]

    state = load_state()

    # Check Gemini active profile for API key
    gemini_active = state.get("active", {}).get("gemini")
    if gemini_active:
        profile_dir = get_config_dir() / "profiles" / "gemini" / gemini_active
        api_key_file = profile_dir / "api_key.txt"
        if api_key_file.exists():
            key = api_key_file.read_text().strip()
            if key:
                lines.append(f'export GEMINI_API_KEY="{key}"')

    # Check Codex active profile for API key
    codex_active = state.get("active", {}).get("codex")
    if codex_active:
        profile_dir = get_config_dir() / "profiles" / "codex" / codex_active
        auth_file = profile_dir / "auth.json"
        if auth_file.exists():
            try:
                data = json.loads(auth_file.read_text())
                key = data.get("OPENAI_API_KEY", "")
                if key:
                    lines.append(f'export OPENAI_API_KEY="{key}"')
            except json.JSONDecodeError:
                pass

    env_sh.write_text("\n".join(lines) + "\n")


# ---------------------------------------------------------------------------
# Bin symlink
# ---------------------------------------------------------------------------


def install_bin_symlink() -> bool:
    """Create ~/.local/bin/switcher symlink to main.py."""
    from pathlib import Path

    bin_dir = Path.home() / ".local" / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    link = bin_dir / "switcher"

    # Find main.py
    main_py = Path(__file__).resolve().parent.parent / "main.py"
    if not main_py.exists():
        print_warning(f"main.py not found at {main_py}")
        return False

    if link.exists() or link.is_symlink():
        link.unlink()

    link.symlink_to(main_py)
    # Ensure main.py is executable
    main_py.chmod(main_py.stat().st_mode | 0o755)
    return True


def remove_bin_symlink() -> bool:
    """Remove ~/.local/bin/switcher symlink."""
    from pathlib import Path

    link = Path.home() / ".local" / "bin" / "switcher"
    if link.is_symlink() or link.exists():
        link.unlink()
        return True
    return False


# ---------------------------------------------------------------------------
# Copy hook scripts to config dir
# ---------------------------------------------------------------------------


def copy_hook_scripts() -> None:
    """Copy hook .py files to ~/.config/cli-switcher/hooks/."""
    src_dir = __import__("pathlib").Path(__file__).resolve().parent / "hooks"
    dest_dir = get_config_dir() / "hooks"
    dest_dir.mkdir(parents=True, exist_ok=True)

    for src in src_dir.glob("*.py"):
        if src.name == "__init__.py":
            continue
        dest = dest_dir / src.name
        shutil.copy2(src, dest)


# ---------------------------------------------------------------------------
# Orchestrators
# ---------------------------------------------------------------------------


def run_install() -> None:
    """Run all installation steps."""
    print_info("Installing CLI Switcher integration...\n")
    results: list[tuple[str, bool]] = []

    # 1. Shell RC
    shell = detect_shell()
    rc = get_rc_file(shell)
    injected = inject_into_rc(rc)
    results.append((f"Shell integration ({rc})", injected))

    # 2. Copy hook scripts
    copy_hook_scripts()
    results.append(("Hook scripts copied", True))

    # 3. Gemini hooks
    hooks_added = install_gemini_hooks()
    results.append(("Gemini hooks (settings.json)", hooks_added))

    # 4. Slash command
    slash = install_slash_command()
    results.append(("Gemini /change command", slash))

    # 5. env.sh
    generate_env_sh()
    results.append(("env.sh generated", True))

    # 6. Bin symlink
    linked = install_bin_symlink()
    results.append(("~/.local/bin/switcher symlink", linked))

    # Summary
    print()
    for label, was_new in results:
        if was_new:
            print_success(f"  ✔ {label}")
        else:
            print_info(f"  • {label} (already present)")

    print()
    if any(r[1] for r in results):
        print_info(f"Restart your shell or run: source {rc}")
    else:
        print_info("Everything already installed.")


def run_uninstall() -> None:
    """Run all uninstallation steps."""
    print_info("Removing CLI Switcher integration...\n")
    results: list[tuple[str, bool]] = []

    # 1. Shell RC
    shell = detect_shell()
    rc = get_rc_file(shell)
    removed_rc = remove_from_rc(rc)
    results.append((f"Shell integration ({rc})", removed_rc))

    # 2. Gemini hooks
    removed_hooks = remove_gemini_hooks()
    results.append(("Gemini hooks (settings.json)", removed_hooks))

    # 3. Slash command
    removed_slash = remove_slash_command()
    results.append(("Gemini /change command", removed_slash))

    # 4. Bin symlink
    removed_link = remove_bin_symlink()
    results.append(("~/.local/bin/switcher symlink", removed_link))

    # Note: we don't delete env.sh or hook scripts — they're harmless

    # Summary
    print()
    for label, was_removed in results:
        if was_removed:
            print_success(f"  ✔ Removed: {label}")
        else:
            print_info(f"  • {label} (not found)")

    if any(r[1] for r in results):
        print()
        print_info(f"Restart your shell or run: source {rc}")
