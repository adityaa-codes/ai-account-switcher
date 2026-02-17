"""CLI argument parsing
and command routing for cli-switcher."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

from switcher import __version__
from switcher.config import (
    get_config_value,
    load_config,
    set_config_value,
)
from switcher.errors import SwitcherError
from switcher.profiles.codex import CodexProfileManager
from switcher.profiles.gemini import GeminiProfileManager
from switcher.state import get_active_profile
from switcher.ui import (
    confirm,
    print_dashboard,
    print_error,
    print_info,
    print_profile_list,
    print_success,
    print_warning,
)
from switcher.utils import ensure_dirs, setup_logging

if TYPE_CHECKING:
    from switcher.profiles.base import ProfileManager

logger = logging.getLogger("switcher.cli")


def _get_manager(cli_name: str) -> ProfileManager:
    """Return the profile manager for a CLI name."""
    if cli_name == "gemini":
        return GeminiProfileManager()
    return CodexProfileManager()


# ── Command handlers ──────────────────────────────────────────────


def cmd_status(_args: argparse.Namespace) -> None:
    """Show dashboard of all CLIs."""
    gm = GeminiProfileManager()
    cm = CodexProfileManager()
    config = load_config()

    gemini_profiles = [
        {"label": p.label, "auth_type": p.auth_type, **p.meta}
        for p in gm.list_profiles()
    ]
    codex_profiles = [
        {"label": p.label, "auth_type": p.auth_type, **p.meta}
        for p in cm.list_profiles()
    ]

    print_dashboard(
        gemini_profiles=gemini_profiles,
        gemini_active=get_active_profile("gemini"),
        codex_profiles=codex_profiles,
        codex_active=get_active_profile("codex"),
        auto_rotate=config["auto_rotate"]["enabled"],
    )


def cmd_list(_args: argparse.Namespace, cli_name: str) -> None:
    """List profiles for a CLI."""
    mgr = _get_manager(cli_name)
    profiles = mgr.list_profiles()
    active = get_active_profile(cli_name)
    profile_dicts = [
        {"label": p.label, "auth_type": p.auth_type, **p.meta} for p in profiles
    ]
    print_profile_list(profile_dicts, active, cli_name)


def cmd_switch(args: argparse.Namespace, cli_name: str) -> None:
    """Switch to a profile."""
    mgr = _get_manager(cli_name)
    label = mgr.switch_to(args.target)
    print_success(f"Switched {cli_name} to: {label}")

    profile = mgr.get_profile(args.target)
    if profile.auth_type == "oauth":
        print_info(f"Restart {cli_name} CLI to apply OAuth changes.")
    elif profile.auth_type == "chatgpt":
        print_info(f"Restart {cli_name} CLI to apply ChatGPT OAuth changes.")


def cmd_next(_args: argparse.Namespace, cli_name: str) -> None:
    """Rotate to next profile."""
    mgr = _get_manager(cli_name)
    label = mgr.switch_next()
    print_success(f"Rotated {cli_name} to: {label}")


def cmd_add(args: argparse.Namespace, cli_name: str) -> None:
    """Add a new profile."""
    label = args.label
    if not label:
        try:
            label = input(f"Enter profile label for {cli_name}: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if not label:
            print_error("Label cannot be empty.")
            return

    # Determine auth type
    if cli_name == "gemini":
        auth_choices = ["oauth", "apikey"]
    else:
        auth_choices = ["apikey", "chatgpt"]

    auth_type = getattr(args, "type", None)
    if not auth_type:
        try:
            print(f"  Auth types: {', '.join(auth_choices)}")
            auth_type = input("  Auth type: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return

    if auth_type not in auth_choices:
        print_error(
            f"Invalid auth type '{auth_type}'. Choose from: {', '.join(auth_choices)}"
        )
        return

    mgr = _get_manager(cli_name)
    profile = mgr.add_profile(label, auth_type)
    print_success(f"Created {cli_name} profile: {profile.label}")

    if auth_type == "apikey":
        if cli_name == "gemini":
            key_path = profile.path / "api_key.txt"
            print_info(f"Add your API key to: {key_path}")
        else:
            auth_path = profile.path / "auth.json"
            if not auth_path.exists():
                print_info(f"Add your auth.json to: {auth_path}")


def cmd_remove(args: argparse.Namespace, cli_name: str) -> None:
    """Remove a profile."""
    mgr = _get_manager(cli_name)
    profile = mgr.get_profile(args.target)

    if not confirm(f"Remove {cli_name} profile '{profile.label}'?"):
        print_info("Cancelled.")
        return

    label = mgr.remove_profile(args.target)
    print_success(f"Removed {cli_name} profile: {label}")


def cmd_import(args: argparse.Namespace, cli_name: str) -> None:
    """Import credentials from a file."""
    path = Path(args.path)
    label = args.label
    if not label:
        label = path.stem  # Use filename without extension

    mgr = _get_manager(cli_name)
    profile = mgr.import_credentials(path, label)
    print_success(f"Imported as '{profile.label}' ({profile.auth_type})")


def cmd_health(_args: argparse.Namespace, cli_name: str) -> None:
    """Check health of all profiles."""
    # Health check implementation in Phase 5
    print_warning(f"Health checks for {cli_name} not yet implemented.")


def cmd_config(args: argparse.Namespace) -> None:
    """View or set config values."""
    if args.key is None:
        # Show all config
        config = load_config()
        _print_config(config)
        return

    if args.value is None:
        # Get single value
        try:
            value = get_config_value(args.key)
            print(f"  {args.key} = {value!r}")
        except SwitcherError as exc:
            print_error(str(exc))
        return

    # Set value
    try:
        set_config_value(args.key, args.value)
        print_success(f"Set {args.key} = {args.value!r}")
    except SwitcherError as exc:
        print_error(str(exc))


def _print_config(config: dict[str, Any], prefix: str = "") -> None:
    """Recursively print config key-value pairs."""
    for key, value in config.items():
        full_key = f"{prefix}{key}" if not prefix else f"{prefix}.{key}"
        if isinstance(value, dict):
            _print_config(value, full_key)
        else:
            print(f"  {full_key} = {value!r}")


def cmd_install(_args: argparse.Namespace) -> None:
    """Install shell + hook integration."""
    # Installer implementation in Phase 7
    print_warning("Install not yet implemented.")


def cmd_uninstall(_args: argparse.Namespace) -> None:
    """Remove shell + hook integration."""
    # Uninstaller implementation in Phase 7
    print_warning("Uninstall not yet implemented.")


def cmd_version(_args: argparse.Namespace) -> None:
    """Print version."""
    print(f"cli-switcher {__version__}")


# ── Parser construction ───────────────────────────────────────────


def _add_cli_subcommands(
    subparsers: argparse._SubParsersAction,  # type: ignore[type-arg]
    cli_name: str,
) -> None:
    """Add subcommands for a specific CLI (gemini or codex)."""
    cli_parser = subparsers.add_parser(cli_name, help=f"Manage {cli_name} profiles")
    cli_sub = cli_parser.add_subparsers(dest="action")

    # list
    cli_sub.add_parser("list", help="List profiles")

    # switch
    switch_p = cli_sub.add_parser("switch", help="Switch profile")
    switch_p.add_argument("target", help="Profile index (1-based) or label")

    # next
    cli_sub.add_parser("next", help="Rotate to next profile")

    # add
    add_p = cli_sub.add_parser("add", help="Add new profile")
    add_p.add_argument("label", nargs="?", help="Profile label")
    add_p.add_argument("--type", "-t", dest="type", help="Auth type")

    # remove
    rm_p = cli_sub.add_parser("remove", help="Remove profile")
    rm_p.add_argument("target", help="Profile index (1-based) or label")

    # import
    imp_p = cli_sub.add_parser("import", help="Import credentials file")
    imp_p.add_argument("path", help="Path to credentials file")
    imp_p.add_argument("label", nargs="?", help="Profile label")

    # health
    cli_sub.add_parser("health", help="Check profile health")


def build_parser() -> argparse.ArgumentParser:
    """Construct the argparse parser with all subcommands."""
    parser = argparse.ArgumentParser(
        prog="switcher",
        description="Unified multi-account manager for Gemini CLI and Codex CLI",
    )

    subparsers = parser.add_subparsers(dest="command")

    # status (default when no command given)
    subparsers.add_parser("status", help="Show status dashboard")

    # gemini / codex subcommands
    _add_cli_subcommands(subparsers, "gemini")
    _add_cli_subcommands(subparsers, "codex")

    # config
    config_p = subparsers.add_parser("config", help="View or set config")
    config_p.add_argument("key", nargs="?", help="Config key")
    config_p.add_argument("value", nargs="?", help="Config value")

    # install / uninstall
    subparsers.add_parser("install", help="Install shell + hook integration")
    subparsers.add_parser("uninstall", help="Remove shell + hook integration")

    # version
    subparsers.add_parser("version", help="Print version")

    return parser


# ── Routing ───────────────────────────────────────────────────────

# Map of (command, action) → handler
_CLI_ACTIONS: dict[str, Any] = {
    "list": cmd_list,
    "switch": cmd_switch,
    "next": cmd_next,
    "add": cmd_add,
    "remove": cmd_remove,
    "import": cmd_import,
    "health": cmd_health,
}


def main() -> None:
    """Entry point — parse args, route to handler, handle errors."""
    ensure_dirs()

    parser = build_parser()
    args = parser.parse_args()

    # Set up logging
    try:
        config = load_config()
        log_level = config["general"]["log_level"]
    except Exception:
        log_level = "info"
    setup_logging(log_level)

    try:
        _dispatch(parser, args)
    except SwitcherError as exc:
        print_error(str(exc))
        logger.error("%s: %s", type(exc).__name__, exc)
        sys.exit(1)
    except KeyboardInterrupt:
        print()
        sys.exit(130)


def _dispatch(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    """Route parsed args to the correct command handler."""
    command = args.command

    # Default to status when no command
    if command is None or command == "status":
        cmd_status(args)
        return

    if command == "config":
        cmd_config(args)
        return

    if command == "install":
        cmd_install(args)
        return

    if command == "uninstall":
        cmd_uninstall(args)
        return

    if command == "version":
        cmd_version(args)
        return

    # CLI-specific commands (gemini/codex)
    if command in ("gemini", "codex"):
        action = getattr(args, "action", None)
        if action is None:
            # No action → list profiles
            cmd_list(args, command)
            return

        handler = _CLI_ACTIONS.get(action)
        if handler:
            handler(args, command)
            return

    parser.print_help()
