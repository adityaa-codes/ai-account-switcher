"""Terminal output — colors, tables, dashboard rendering."""

from __future__ import annotations

import os
import sys
from typing import Any

from switcher import __version__

# Health status indicators
_HEALTH_ICONS: dict[str, str] = {
    "valid": "✅",
    "expiring": "⚠️ ",
    "expired": "❌",
    "revoked": "🚫",
    "unknown": "❓",
}

# Auth type display labels
_AUTH_LABELS: dict[str, str] = {
    "oauth": "OAuth",
    "apikey": "API Key",
    "chatgpt": "ChatGPT",
}


def _colors_enabled() -> bool:
    """Check if ANSI colors should be used."""
    if os.environ.get("NO_COLOR"):
        return False
    if not hasattr(sys.stdout, "isatty") or not sys.stdout.isatty():
        return False
    term = os.environ.get("TERM", "")
    return term != "dumb"


class _Colors:
    """ANSI color codes, disabled when output is not a TTY."""

    def __init__(self) -> None:
        enabled = _colors_enabled()
        self.reset = "\033[0m" if enabled else ""
        self.bold = "\033[1m" if enabled else ""
        self.dim = "\033[2m" if enabled else ""
        self.green = "\033[32m" if enabled else ""
        self.red = "\033[31m" if enabled else ""
        self.yellow = "\033[33m" if enabled else ""
        self.blue = "\033[34m" if enabled else ""
        self.cyan = "\033[36m" if enabled else ""


C = _Colors()


def print_success(msg: str) -> None:
    """Print a green success message."""
    print(f"{C.green}✅ {msg}{C.reset}")


def print_error(msg: str) -> None:
    """Print a red error message to stderr."""
    print(f"{C.red}❌ {msg}{C.reset}", file=sys.stderr)


def print_warning(msg: str) -> None:
    """Print a yellow warning message."""
    print(f"{C.yellow}⚠️  {msg}{C.reset}")


def print_info(msg: str) -> None:
    """Print a blue info message."""
    print(f"{C.blue}\N{INFORMATION SOURCE}\ufe0f  {msg}{C.reset}")


def print_table(headers: list[str], rows: list[list[str]]) -> None:
    """Print a simple aligned table.

    Args:
        headers: Column header strings.
        rows: List of row data (each row is a list of strings).
    """
    if not rows:
        print(f"{C.dim}  (no entries){C.reset}")
        return

    # Calculate column widths
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            if i < len(widths):
                widths[i] = max(widths[i], len(cell))

    # Print header
    header_line = "  ".join(h.ljust(widths[i]) for i, h in enumerate(headers))
    print(f"{C.bold}  {header_line}{C.reset}")
    print(f"  {'  '.join('─' * w for w in widths)}")

    # Print rows
    for row in rows:
        cells = []
        for i, cell in enumerate(row):
            width = widths[i] if i < len(widths) else len(cell)
            cells.append(cell.ljust(width))
        print(f"  {'  '.join(cells)}")


def print_profile_list(
    profiles: list[dict[str, Any]], active: str | None, cli_name: str
) -> None:
    """Print a formatted profile listing.

    Args:
        profiles: List of profile dicts with 'label', 'auth_type', 'health_status'.
        active: Label of the currently active profile.
        cli_name: 'gemini' or 'codex'.
    """
    print(f"\n{C.bold}  {cli_name.upper()} CLI{C.reset}")
    print(f"  {'─' * 40}")

    if not profiles:
        print(f"  {C.dim}No profiles configured.{C.reset}")
        print(f"  Run: switcher {cli_name} add")
        return

    headers = ["#", "", "Label", "Type", "Health"]
    rows: list[list[str]] = []
    for i, p in enumerate(profiles, 1):
        is_active = p.get("label") == active
        marker = "●" if is_active else "○"
        auth = _AUTH_LABELS.get(p.get("auth_type", ""), p.get("auth_type", ""))
        health = p.get("health_status", "unknown")
        icon = _HEALTH_ICONS.get(health, "❓")
        rows.append([f"{i:02d}.", marker, p.get("label", ""), auth, f"{icon} {health}"])

    print_table(headers, rows)


def print_dashboard(
    gemini_profiles: list[dict[str, Any]],
    gemini_active: str | None,
    codex_profiles: list[dict[str, Any]],
    codex_active: str | None,
    auto_rotate: bool = False,
) -> None:
    """Print the full status dashboard.

    Args:
        gemini_profiles: List of Gemini profile dicts.
        gemini_active: Active Gemini profile label.
        codex_profiles: List of Codex profile dicts.
        codex_active: Active Codex profile label.
        auto_rotate: Whether auto-rotation is enabled.
    """
    print(f"\n{C.bold}  CLI Switcher v{__version__}{C.reset}")
    print(f"  {'═' * 50}")

    # Gemini section
    print_profile_list(gemini_profiles, gemini_active, "gemini")
    rotate_status = f"{C.green}ON{C.reset}" if auto_rotate else f"{C.dim}OFF{C.reset}"
    print(f"  Auto-rotate: {rotate_status}")

    # Codex section
    print_profile_list(codex_profiles, codex_active, "codex")

    print(f"  {'═' * 50}\n")


def confirm(prompt: str) -> bool:
    """Ask user for y/N confirmation.

    Args:
        prompt: The question to display.

    Returns:
        True if user confirmed, False otherwise.
    """
    try:
        answer = input(f"{prompt} [y/N] ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return False
    return answer in ("y", "yes")
