"""Interactive profile management menu for Gemini and Codex CLIs."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import argparse


# ---------------------------------------------------------------------------
# Menu action definitions
# ---------------------------------------------------------------------------

_GEMINI_ACTIONS: list[tuple[str, str]] = [
    ("list", "List all profiles"),
    ("switch", "Switch to a profile"),
    ("next", "Rotate to next profile"),
    ("quota", "Show live quota usage"),
    ("health", "Check profile health"),
    ("add", "Add a new profile"),
    ("import", "Import credentials"),
    ("config", "Toggle auto-rotate on/off"),
]

_CODEX_ACTIONS: list[tuple[str, str]] = [
    ("list", "List all profiles"),
    ("switch", "Switch to a profile"),
    ("next", "Rotate to next profile"),
    ("health", "Check profile health"),
    ("add", "Add a new profile"),
    ("import", "Import credentials"),
]


def _actions_for(cli_name: str) -> list[tuple[str, str]]:
    return _GEMINI_ACTIONS if cli_name == "gemini" else _CODEX_ACTIONS


def _print_menu_header(cli_name: str) -> None:
    """Print the menu header with current active profile."""
    from switcher.state import get_active_profile
    from switcher.ui import C

    active = get_active_profile(cli_name) or "(none)"
    print()
    print(f"{C.bold}{C.cyan}  {cli_name.capitalize()} Profile Manager{C.reset}")
    print(f"  Active: {active}")
    print(f"  {'─' * 36}")


def _print_menu_choices(cli_name: str) -> None:
    actions = _actions_for(cli_name)
    for i, (_, description) in enumerate(actions, 1):
        print(f"  {i:>2})  {description}")
    print("   q)  Quit")
    print()


def _handle_choice(
    choice: str,
    cli_name: str,
    parser: argparse.ArgumentParser,
) -> bool:
    """Dispatch a menu choice. Return False to quit, True to continue.

    Args:
        choice: User input string (number or 'q').
        cli_name: 'gemini' or 'codex'.
        parser: The root argparse parser (used to build fake Namespace objects).

    Returns:
        False if the user wants to quit, True otherwise.
    """
    import argparse as _ap

    from switcher.ui import print_error

    if choice.lower() in ("q", "quit", "exit"):
        return False

    actions = _actions_for(cli_name)
    try:
        idx = int(choice) - 1
        if idx < 0 or idx >= len(actions):
            raise ValueError
    except ValueError:
        print_error(f"  Invalid choice: {choice!r}")
        return True

    action_key, _ = actions[idx]

    # Build a minimal Namespace and delegate to the existing CLI handlers.
    from switcher import cli as _cli

    args = _ap.Namespace(command=cli_name, action=action_key)

    try:
        if action_key == "switch":
            target = input("  Profile index or label: ").strip()
            if not target:
                return True
            args.target = target
            _cli.cmd_switch(args, cli_name)

        elif action_key == "add":
            label = input("  Label for new profile (leave blank for auto): ").strip()
            args.label = label or None
            args.type = None
            _cli.cmd_add(args, cli_name)

        elif action_key == "import":
            path = input("  Path to credentials file: ").strip()
            if not path:
                return True
            label = input("  Label (leave blank to use filename): ").strip()
            args.path = path
            args.label = label or None
            _cli.cmd_import(args, cli_name)

        elif action_key == "config":
            _toggle_auto_rotate()

        elif action_key == "list":
            _cli.cmd_list(args, cli_name)

        elif action_key == "next":
            _cli.cmd_next(args, cli_name)

        elif action_key == "quota":
            _cli.cmd_quota(args, cli_name)

        elif action_key == "health":
            _cli.cmd_health(args, cli_name)

    except KeyboardInterrupt:
        print()
    except Exception as exc:
        print_error(f"  Error: {exc}")

    return True


def _toggle_auto_rotate() -> None:
    """Toggle auto_rotate.enabled in config and print the new value."""
    from switcher.config import get_config_value, set_config_value
    from switcher.ui import print_success

    current = get_config_value("auto_rotate.enabled")
    new_val = not bool(current)
    set_config_value("auto_rotate.enabled", new_val)
    state = "enabled" if new_val else "disabled"
    print_success(f"  Auto-rotate {state}.")


def _non_interactive_help(cli_name: str) -> None:
    """Print a compact command reference when stdin is not a TTY."""
    from switcher.ui import C

    actions = _actions_for(cli_name)
    print(f"\n{C.bold}  switcher {cli_name} — available commands:{C.reset}")
    for action_key, description in actions:
        print(f"    switcher {cli_name} {action_key:<10}  {description}")
    print()


def run_menu(cli_name: str, parser: argparse.ArgumentParser) -> None:
    """Run the interactive profile management menu.

    Falls back to a non-interactive command listing when stdin is not a TTY
    (e.g., when called from a script or pipe).

    Args:
        cli_name: 'gemini' or 'codex'.
        parser: Root argparse parser used for help generation.
    """
    if not sys.stdin.isatty():
        _non_interactive_help(cli_name)
        return

    try:
        while True:
            _print_menu_header(cli_name)
            _print_menu_choices(cli_name)
            try:
                choice = input("  Choice: ").strip()
            except EOFError:
                break
            if not _handle_choice(choice, cli_name, parser):
                break
    except KeyboardInterrupt:
        print()
