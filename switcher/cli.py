"""CLI argument parsing
and command routing for ai-account-switcher."""

from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
import time
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


def _recover_profile_oauth_from_keyring(profile: Profile) -> bool:
    """Recover oauth_creds.json from Gemini keyring entry when available."""
    from switcher.auth.gemini_auth import (
        GEMINI_KEYRING_KEY,
        GEMINI_KEYRING_SERVICE,
        convert_from_keyring_format,
    )
    from switcher.auth.keyring_backend import keyring_read

    try:
        keyring_blob = keyring_read(GEMINI_KEYRING_SERVICE, GEMINI_KEYRING_KEY)
    except Exception:
        logger.debug("Could not read Gemini keyring entry", exc_info=True)
        return False
    if not keyring_blob:
        return False

    try:
        keyring_payload = json.loads(keyring_blob)
    except json.JSONDecodeError:
        return False
    if not isinstance(keyring_payload, dict):
        return False

    oauth_payload = convert_from_keyring_format(keyring_payload)
    token = oauth_payload.get("token", oauth_payload)
    if not isinstance(token, dict):
        return False
    has_tokens = bool(
        token.get("refreshToken")
        or token.get("refresh_token")
        or token.get("accessToken")
        or token.get("access_token")
    )
    if not has_tokens:
        return False

    creds_path = profile.path / "oauth_creds.json"
    creds_path.write_text(json.dumps(oauth_payload, indent=2) + "\n", encoding="utf-8")
    (profile.path / "keyring_creds.json").write_text(keyring_blob, encoding="utf-8")
    logger.info(
        "Recovered oauth_creds.json from keyring for profile '%s'", profile.label
    )
    return True


def _recover_profile_oauth_from_profile_keyring_backup(profile: Profile) -> bool:
    """Recover oauth_creds.json from profile-local keyring backup."""
    from switcher.auth.gemini_auth import convert_from_keyring_format

    keyring_path = profile.path / "keyring_creds.json"
    if not keyring_path.exists():
        return False

    try:
        keyring_payload = json.loads(keyring_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    if not isinstance(keyring_payload, dict):
        return False

    oauth_payload = convert_from_keyring_format(keyring_payload)
    token = oauth_payload.get("token", oauth_payload)
    if not isinstance(token, dict):
        return False
    has_tokens = bool(
        token.get("refreshToken")
        or token.get("refresh_token")
        or token.get("accessToken")
        or token.get("access_token")
    )
    if not has_tokens:
        return False

    creds_path = profile.path / "oauth_creds.json"
    creds_path.write_text(json.dumps(oauth_payload, indent=2) + "\n", encoding="utf-8")
    logger.info(
        "Recovered oauth_creds.json from profile keyring backup for '%s'",
        profile.label,
    )
    return True


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
        _recover_profile_oauth_from_keyring(profile)

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

    if cli_name == "gemini" and profile.auth_type == "oauth":
        if not _profile_has_oauth_creds(profile):
            _recover_profile_oauth_from_profile_keyring_backup(profile)
        if not _profile_has_oauth_creds(profile):
            _recover_profile_oauth_from_keyring(profile)
        if not _profile_has_oauth_creds(profile):
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


def cmd_pool_status(_args: argparse.Namespace, cli_name: str) -> None:
    """Show a compact one-liner status for each profile in the pool.

    Displays: index, label, auth type, health status, and last-used timestamp.
    """
    from switcher.health import check_profile

    mgr = _get_manager(cli_name)
    profiles = mgr.list_profiles()
    if not profiles:
        print_warning(f"No {cli_name} profiles configured.")
        return

    active = get_active_profile(cli_name)
    _HEALTH_ICONS: dict[str, str] = {
        "valid": "✅",
        "expiring": "⚠️ ",
        "expired": "❌",
        "revoked": "🚫",
        "unknown": "❓",
    }
    for i, profile in enumerate(profiles, 1):
        marker = "▶" if profile.label == active else " "
        status, _detail = check_profile(cli_name, profile)
        icon = _HEALTH_ICONS.get(status, "❓")
        last_used = profile.meta.get("last_used", "never")
        print(
            f"  {marker} {i:02d}. {profile.label:<24} "
            f"{profile.auth_type:<8} {icon} {status:<10}  "
            f"last: {last_used}"
        )


def _quota_bar(pct: float, width: int = 10) -> str:
    """Render a Unicode progress bar for quota remaining percentage.

    Args:
        pct: Percentage remaining (0-100).
        width: Bar character width.

    Returns:
        A string like '████████░░' representing the fill level.
    """
    filled = round(max(0.0, min(100.0, pct)) / 100 * width)
    return "█" * filled + "░" * (width - filled)


def _format_reset_date(iso_str: str) -> str:
    """Format an ISO 8601 reset timestamp into a human-readable string.

    Args:
        iso_str: ISO 8601 date/datetime string.

    Returns:
        Formatted string like 'Apr 1 2025', or the original string on error.
    """
    from datetime import datetime, timezone

    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00")).astimezone(
            timezone.utc
        )
        day = str(dt.day)  # portable — no %-d GNU extension
        return dt.strftime(f"%b {day} %Y")
    except (ValueError, AttributeError):
        return iso_str


def cmd_health(_args: argparse.Namespace, cli_name: str) -> None:
    """Check health of all profiles, including quota usage for Gemini OAuth."""
    from switcher.health import ProfileQuotaInfo, check_all_profiles
    from switcher.ui import print_table

    _HEALTH_ICONS: dict[str, str] = {
        "valid": "✅",
        "expiring": "⚠️ ",
        "expired": "❌",
        "revoked": "🚫",
        "unknown": "❓",
    }

    mgr = _get_manager(cli_name)
    profiles = mgr.list_profiles()
    if not profiles:
        print_warning(f"No {cli_name} profiles configured.")
        return

    print_info(f"Checking {cli_name} profiles...")
    results = check_all_profiles(cli_name, profiles)

    headers = ["#", "Label", "Email", "Status", "Detail"]
    rows: list[list[str]] = []
    for i, (profile, status, detail, quota_info) in enumerate(results, 1):
        email = ""
        if quota_info and quota_info.email:
            email = quota_info.email
        elif profile.meta.get("email"):
            email = str(profile.meta["email"])
        icon = _HEALTH_ICONS.get(status, "❓")
        rows.append([f"{i:02d}.", profile.label, email, f"{icon} {status}", detail])

    print()
    print_table(headers, rows)

    # Quota section (Gemini OAuth only)
    quota_results = [
        (p, qi)
        for p, _s, _d, qi in results
        if qi is not None and (qi.quotas or qi.error)
    ]
    if not quota_results:
        return

    print("\n  Quota Usage")
    print(f"  {'─' * 62}")
    for profile, quota_info in quota_results:
        assert isinstance(quota_info, ProfileQuotaInfo)
        email_str = f"  ({quota_info.email})" if quota_info.email else ""
        tier_str = f"  [{quota_info.tier}]" if quota_info.tier else ""
        print(f"\n  {profile.label}{email_str}{tier_str}")
        if quota_info.error and not quota_info.quotas:
            print(f"    ⚠️  {quota_info.error}")
            continue
        for q in quota_info.quotas:
            used_pct = 100.0 - q.remaining_pct
            bar = _quota_bar(used_pct)
            warn = " ⚠️" if q.remaining_pct < 20 else ""
            reset_str = ""
            if q.reset_at:
                reset_str = f"  resets {_format_reset_date(str(q.reset_at))}"
            print(
                f"    {q.model:<28} {bar}  {used_pct:5.1f}% used{warn}{reset_str}"
            )


def cmd_quota(_args: argparse.Namespace, cli_name: str) -> None:
    """Show live quota usage for Gemini OAuth profiles.

    Only meaningful for Gemini — Codex does not expose a quota API.
    """
    if cli_name != "gemini":
        print_warning("Quota checking is only available for Gemini CLI profiles.")
        return

    from switcher.health import fetch_quota_info

    mgr = _get_manager(cli_name)
    oauth_profiles = [p for p in mgr.list_profiles() if p.auth_type == "oauth"]

    if not oauth_profiles:
        print_warning("No Gemini OAuth profiles configured.")
        return

    print_info(f"Fetching quota for {len(oauth_profiles)} OAuth profile(s)...")
    print(f"\n  {'─' * 62}")

    for profile in oauth_profiles:
        active_label = get_active_profile(cli_name)
        active_marker = " ●" if profile.label == active_label else ""
        print(f"\n  {profile.label}{active_marker}")

        qi = fetch_quota_info(profile)

        if qi.email:
            print(f"  ({qi.email})")

        if qi.error and not qi.quotas:
            print_warning(f"    {qi.error}")
            continue

        if not qi.quotas:
            print("    No quota data available.")
            continue

        for q in qi.quotas:
            used_pct = 100.0 - q.remaining_pct
            bar = _quota_bar(used_pct)
            warn = " ⚠️" if q.remaining_pct < 20 else ""
            reset_str = ""
            if q.reset_at:
                reset_str = f"  resets {_format_reset_date(str(q.reset_at))}"
            print(
                f"    {q.model:<28} {bar}  {used_pct:5.1f}% used{warn}{reset_str}"
            )

    print()


def cmd_change(args: argparse.Namespace, cli_name: str) -> None:
    """Switch profile — slash-command parity for /change.

    Routing:
        No target or 'next'  → rotate to next profile (same as ``gemini next``)
        Numeric string       → switch to that 1-based index
        Any other string     → switch by label
    """
    target: str | None = getattr(args, "target", None)

    if not target or target.lower() == "next":
        cmd_next(args, cli_name)
        return

    # Delegate to switch — args already has .target set
    cmd_switch(args, cli_name)


def cmd_menu(_args: argparse.Namespace, cli_name: str) -> None:
    """Launch the interactive profile management menu."""
    from switcher.ui_menu import run_menu

    run_menu(cli_name, build_parser())


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


def cmd_setup(_args: argparse.Namespace) -> None:
    """Run guided setup workflow (implementation added in follow-up task)."""
    print_info("Setup workflow is being prepared. For now run: switcher install")


def cmd_alerts(args: argparse.Namespace) -> None:
    """Show recent error log entries from errors.log.

    Args:
        args: Parsed arguments; ``args.lines`` controls how many lines to show.
    """
    from switcher.utils import get_config_dir

    errors_log = get_config_dir() / "logs" / "errors.log"
    n_lines: int = getattr(args, "lines", 20) or 20

    if not errors_log.exists():
        print_info("No errors log found — everything looks clean!")
        return

    try:
        text = errors_log.read_text(encoding="utf-8", errors="replace")
        all_lines = text.splitlines()
        tail = all_lines[-n_lines:]
        if not tail:
            print_info("errors.log is empty.")
            return
        print_info(f"Last {len(tail)} entries from errors.log:")
        print()
        for line in tail:
            print(f"  {line}")
    except OSError as exc:
        print_warning(f"Could not read errors.log: {exc}")


def _parse_exported_env(env_path: Path) -> dict[str, str]:
    """Parse exported env vars from env.sh."""
    parsed: dict[str, str] = {}
    if not env_path.exists():
        return parsed

    for raw in env_path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line.startswith("export "):
            continue
        key_value = line.removeprefix("export ").strip()
        if "=" not in key_value:
            continue
        key, value = key_value.split("=", 1)
        parsed[key.strip()] = value.strip().strip('"').strip("'")
    return parsed


def cmd_doctor(_args: argparse.Namespace) -> None:
    """Run auth diagnostics for common OAuth/API-key conflict scenarios."""
    from switcher.utils import get_codex_dir, get_config_dir, get_gemini_dir

    issues: list[str] = []

    env_file = get_config_dir() / "env.sh"
    try:
        file_env = _parse_exported_env(env_file)
    except OSError as exc:
        issues.append(f"Could not read env.sh ({env_file}): {exc}")
        file_env = {}

    process_env = {
        key: os.environ.get(key, "")
        for key in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "OPENAI_API_KEY")
        if os.environ.get(key)
    }

    gm_profiles = {p.label: p for p in GeminiProfileManager().list_profiles()}
    cm_profiles = {p.label: p for p in CodexProfileManager().list_profiles()}
    active_gemini = get_active_profile("gemini")
    active_codex = get_active_profile("codex")

    if active_gemini and active_gemini in gm_profiles:
        profile = gm_profiles[active_gemini]
        if profile.auth_type == "oauth":
            if file_env.get("GEMINI_API_KEY") or file_env.get("GOOGLE_API_KEY"):
                issues.append(
                    "Gemini active profile is OAuth, but env.sh still exports "
                    "GEMINI_API_KEY/GOOGLE_API_KEY."
                )
            if process_env.get("GEMINI_API_KEY") or process_env.get("GOOGLE_API_KEY"):
                issues.append(
                    "Gemini active profile is OAuth, but current shell has "
                    "GEMINI_API_KEY/GOOGLE_API_KEY set."
                )
            if not (profile.path / "oauth_creds.json").exists():
                issues.append(
                    f"Gemini OAuth profile '{profile.label}' is missing "
                    "oauth_creds.json."
                )
            gemini_link = get_gemini_dir() / "oauth_creds.json"
            if gemini_link.exists() and not gemini_link.is_symlink():
                issues.append(
                    "~/.gemini/oauth_creds.json is not a symlink. "
                    "It may contain stale credentials."
                )

    if active_codex and active_codex in cm_profiles:
        profile = cm_profiles[active_codex]
        if profile.auth_type == "chatgpt":
            if file_env.get("OPENAI_API_KEY"):
                issues.append(
                    "Codex active profile is ChatGPT OAuth, but env.sh exports "
                    "OPENAI_API_KEY."
                )
            if process_env.get("OPENAI_API_KEY"):
                issues.append(
                    "Codex active profile is ChatGPT OAuth, but current shell has "
                    "OPENAI_API_KEY set."
                )
            if not (profile.path / "auth.json").exists():
                issues.append(
                    f"Codex ChatGPT profile '{profile.label}' is missing auth.json."
                )
            codex_link = get_codex_dir() / "auth.json"
            if codex_link.exists() and not codex_link.is_symlink():
                issues.append(
                    "~/.codex/auth.json is not a symlink. "
                    "It may contain stale credentials."
                )

    print_info("Running auth diagnostics...")
    if not issues:
        print_success("No auth conflicts detected.")
        return

    print_warning(f"Found {len(issues)} auth issue(s):")
    for item in issues:
        print(f"  - {item}")
    print_info("Suggested fix: run 'switcher uninstall' then 'switcher install'.")


def cmd_version(args: argparse.Namespace) -> None:
    """Print version, optionally checking PyPI for updates."""
    print(f"ai-account-switcher {__version__}")

    if not getattr(args, "check", False):
        return

    try:
        import urllib.request

        url = "https://pypi.org/pypi/ai-account-switcher/json"
        with urllib.request.urlopen(url, timeout=3) as resp:
            data = __import__("json").loads(resp.read())
        latest = data["info"]["version"]
        if latest == __version__:
            print_success("Up to date.")
        else:
            print_warning(
                f"Update available: {latest} — "
                f"pip install -U ai-account-switcher"
            )
    except Exception:
        pass  # silently skip on network error


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

    # change — slash-command parity (/change, /change next, /change 2, /change email)
    change_p = cli_sub.add_parser(
        "change", help="Switch profile (slash-command parity)"
    )
    change_p.add_argument(
        "target",
        nargs="?",
        help="'next', 1-based index, or label (omit to rotate to next)",
    )

    # pool — aliases for list/add/remove/import/health/export/status
    pool_p = cli_sub.add_parser("pool", help="Profile pool aliases")
    pool_sub = pool_p.add_subparsers(dest="pool_action")
    pool_sub.add_parser("list", help="List profiles in the pool")
    pool_add_p = pool_sub.add_parser("add", help="Add profile to the pool")
    pool_add_p.add_argument("label", nargs="?", help="Profile label")
    pool_add_p.add_argument("--type", "-t", dest="type", help="Auth type")
    pool_rm_p = pool_sub.add_parser("remove", help="Remove profile from the pool")
    pool_rm_p.add_argument("target", help="Profile index (1-based) or label")
    pool_imp_p = pool_sub.add_parser("import", help="Import credentials into pool")
    pool_imp_p.add_argument("path", help="Path to credentials file")
    pool_imp_p.add_argument("label", nargs="?", help="Profile label")
    pool_exp_p = pool_sub.add_parser("export", help="Export profile credentials")
    pool_exp_p.add_argument("target", help="Profile index or label")
    pool_exp_p.add_argument("--dest", help="Destination directory")
    pool_sub.add_parser("health", help="Check health of all profiles in the pool")
    pool_sub.add_parser("status", help="One-line status for each profile in the pool")

    # menu — interactive profile management (gemini only)
    cli_sub.add_parser("menu", help="Interactive profile management menu")

    # quota — live quota usage (gemini only)
    if cli_name == "gemini":
        cli_sub.add_parser("quota", help="Show live quota usage")


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
    subparsers.add_parser("setup", help="Run guided setup")

    # alerts — show recent error log entries
    alerts_p = subparsers.add_parser("alerts", help="Show recent error log entries")
    alerts_p.add_argument(
        "--lines", "-n", type=int, default=20,
        help="Number of lines to show (default: 20)",
    )
    subparsers.add_parser("doctor", help="Diagnose auth env and symlink conflicts")

    # version
    version_p = subparsers.add_parser("version", help="Print version")
    version_p.add_argument(
        "--check", action="store_true", help="Check PyPI for updates"
    )

    return parser


# ── Routing ───────────────────────────────────────────────────────

# Map of action → handler for canonical CLI subcommands
_CLI_ACTIONS: dict[str, Any] = {
    "list": cmd_list,
    "switch": cmd_switch,
    "next": cmd_next,
    "add": cmd_add,
    "remove": cmd_remove,
    "import": cmd_import,
    "export": cmd_export,
    "health": cmd_health,
    "quota": cmd_quota,
    "change": cmd_change,
    "menu": cmd_menu,
}

# Pool sub-action → handler mapping (delegates to canonical commands)
_POOL_ACTIONS: dict[str, Any] = {
    "add": cmd_add,
    "remove": cmd_remove,
    "import": cmd_import,
    "list": cmd_list,
    "health": cmd_health,
    "export": cmd_export,
    "status": cmd_pool_status,
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

    cmd_logger = logging.getLogger("switcher.commands")
    cmd_str = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "(status)"
    start = time.monotonic()

    try:
        _dispatch(parser, args)
        elapsed_ms = int((time.monotonic() - start) * 1000)
        cmd_logger.info("OK      [%dms] %s", elapsed_ms, cmd_str)
    except SwitcherError as exc:
        elapsed_ms = int((time.monotonic() - start) * 1000)
        print_error(str(exc))
        logger.error("%s: %s", type(exc).__name__, exc)
        cmd_logger.info(
            "ERROR   [%dms] %s | %s: %s", elapsed_ms, cmd_str, type(exc).__name__, exc
        )
        sys.exit(1)
    except KeyboardInterrupt:
        elapsed_ms = int((time.monotonic() - start) * 1000)
        cmd_logger.info("INTERRUPT [%dms] %s", elapsed_ms, cmd_str)
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

    if command == "setup":
        cmd_setup(args)
        return

    if command == "alerts":
        cmd_alerts(args)
        return

    if command == "doctor":
        cmd_doctor(args)
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

        # pool aliases — route to pool_action or default to list
        if action == "pool":
            pool_action = getattr(args, "pool_action", None)
            pool_handler = _POOL_ACTIONS.get(pool_action or "")
            if pool_handler:
                pool_handler(args, command)
            else:
                cmd_list(args, command)
            return

        handler = _CLI_ACTIONS.get(action)
        if handler:
            handler(args, command)
            return

    parser.print_help()
