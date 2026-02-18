"""CLI argument parsing
and command routing for cli-switcher."""

from __future__ import annotations

import argparse
import json
import logging
import subprocess
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
    from switcher.profiles.base import Profile, ProfileManager

logger = logging.getLogger("switcher.cli")


def _profile_has_oauth_creds(profile: Profile) -> bool:
    """Return True if a profile has non-empty OAuth credentials."""
    creds_path = profile.path / "oauth_creds.json"
    if not creds_path.exists():
        return False

    try:
        payload = json.loads(creds_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return False

    token = payload.get("token", payload)
    if not isinstance(token, dict):
        return False

    return bool(
        token.get("refreshToken")
        or token.get("refresh_token")
        or token.get("accessToken")
        or token.get("access_token")
    )


def _run_gemini_oauth_enrollment(profile: Profile) -> bool:
    """Launch Gemini CLI OAuth flow and capture creds into the profile."""
    from switcher.auth.gemini_auth import (
        GEMINI_KEYRING_KEY,
        GEMINI_KEYRING_SERVICE,
        clear_gemini_cache,
    )
    from switcher.auth.keyring_backend import keyring_delete
    from switcher.utils import atomic_symlink, get_gemini_dir

    creds_path = profile.path / "oauth_creds.json"
    if not creds_path.exists():
        creds_path.write_text("{}\n", encoding="utf-8")

    gemini_dir = get_gemini_dir()
    gemini_dir.mkdir(parents=True, exist_ok=True)
    atomic_symlink(creds_path, gemini_dir / "oauth_creds.json")

    # Force Gemini CLI to request fresh login credentials.
    try:
        keyring_delete(GEMINI_KEYRING_SERVICE, GEMINI_KEYRING_KEY)
    except Exception:
        logger.debug("Failed to clear Gemini OAuth keyring entry", exc_info=True)
    clear_gemini_cache()

    print_info("Launching Gemini CLI. Complete OAuth in the browser, then exit Gemini.")
    try:
        result = subprocess.run(["gemini"], check=False)
    except FileNotFoundError:
        print_error("Gemini CLI not found in PATH. Install it, then retry.")
        return False
    except KeyboardInterrupt:
        print()
        return False

    if result.returncode not in (0, 130):
        print_warning(
            f"Gemini exited with code {result.returncode}. Checking credentials..."
        )

    if not _profile_has_oauth_creds(profile):
        print_warning(f"No OAuth credentials captured for '{profile.label}'.")
        print_info(f"Retry with: switcher gemini switch {profile.label}")
        return False

    print_success(f"Captured Gemini OAuth credentials for: {profile.label}")
    return True


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
    profile = mgr.get_profile(args.target)

    if (
        cli_name == "gemini"
        and profile.auth_type == "oauth"
        and not _profile_has_oauth_creds(profile)
    ):
        print_warning(f"Profile '{profile.label}' has no OAuth credentials yet.")
        if not confirm("Start Gemini OAuth flow now?"):
            print_info("Cancelled.")
            return
        if not _run_gemini_oauth_enrollment(profile):
            return

    label = mgr.switch_to(profile.label)
    print_success(f"Switched {cli_name} to: {label}")
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

    if cli_name == "gemini" and auth_type == "oauth":
        if _profile_has_oauth_creds(profile):
            print_info("Imported existing Gemini OAuth credentials.")
            return

        print_warning("Profile created without OAuth credentials.")
        if confirm("Start Gemini OAuth flow now?"):
            if _run_gemini_oauth_enrollment(profile) and confirm(
                f"Switch to '{profile.label}' now?"
            ):
                cmd_switch(
                    argparse.Namespace(target=profile.label),
                    cli_name="gemini",
                )
        else:
            print_info(
                f"Run `switcher gemini switch {profile.label}` to start OAuth later."
            )
        return

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


def cmd_export(args: argparse.Namespace, cli_name: str) -> None:
    """Export a profile's credentials to a file."""
    mgr = _get_manager(cli_name)
    dest = Path(args.dest) if hasattr(args, "dest") and args.dest else Path.cwd()
    out = mgr.export_profile(args.target, dest)
    print_success(f"Exported to: {out}")


def cmd_health(_args: argparse.Namespace, cli_name: str) -> None:
    """Check health of all profiles."""
    from switcher.health import check_all_profiles
    from switcher.ui import print_table

    mgr = _get_manager(cli_name)
    profiles = mgr.list_profiles()
    if not profiles:
        print_warning(f"No {cli_name} profiles configured.")
        return

    print_info(f"Checking {cli_name} profiles...")
    results = check_all_profiles(cli_name, profiles)

    headers = ["#", "Label", "Status", "Detail"]
    rows: list[list[str]] = []
    for i, (profile, status, detail) in enumerate(results, 1):
        rows.append([f"{i:02d}.", profile.label, status, detail])

    print()
    print_table(headers, rows)


def cmd_config(args: argparse.Namespace) -> None:
    """View or set config values."""
    key = getattr(args, "key", None)
    value = getattr(args, "value", None)
    extra = list(getattr(args, "extra", []) or [])

    if key is None:
        # Show all config
        config = load_config()
        _print_config(config)
        return

    # Explicit subcommand form:
    #   switcher config get <key>
    #   switcher config set <key> <value>
    if key == "get":
        if value is None or extra:
            print_error("Usage: switcher config get <key>")
            return
        # Get single value
        try:
            current = get_config_value(value)
            print(f"  {value} = {current!r}")
        except SwitcherError as exc:
            print_error(str(exc))
        return

    if key == "set":
        if value is None or len(extra) != 1:
            print_error("Usage: switcher config set <key> <value>")
            return
        try:
            set_config_value(value, extra[0])
            print_success(f"Set {value} = {extra[0]!r}")
        except SwitcherError as exc:
            print_error(str(exc))
        return

    # Legacy forms (still supported):
    #   switcher config <key>
    #   switcher config <key> <value>
    if extra:
        print_error("Usage: switcher config [<key> [<value>]]")
        return

    if value is None:
        try:
            current = get_config_value(key)
            print(f"  {key} = {current!r}")
        except SwitcherError as exc:
            print_error(str(exc))
        return

    try:
        set_config_value(key, value)
        print_success(f"Set {key} = {value!r}")
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
    from switcher.installer import run_install

    run_install()


def cmd_uninstall(_args: argparse.Namespace) -> None:
    """Remove shell + hook integration."""
    from switcher.installer import run_uninstall

    run_uninstall()


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

    # export
    exp_p = cli_sub.add_parser("export", help="Export profile credentials")
    exp_p.add_argument("target", help="Profile index (1-based) or label")
    exp_p.add_argument("dest", nargs="?", help="Destination path (file or directory)")

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
    config_p.add_argument("extra", nargs="*", help=argparse.SUPPRESS)

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
    "export": cmd_export,
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
