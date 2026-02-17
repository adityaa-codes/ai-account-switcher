#!/usr/bin/env python3
"""Gemini AfterAgent hook — detect quota errors and auto-switch profiles.

This script runs as a subprocess of Gemini CLI after every agent response.
It reads JSON from stdin, checks for quota error patterns, and triggers
profile rotation when needed.

IMPORTANT: This script must NEVER exit non-zero or output invalid JSON.
Any error → output {} and exit 0.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

# Quota error patterns to match against prompt_response
QUOTA_ERROR_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"429", re.IGNORECASE),
    re.compile(r"Resource\s+exhausted", re.IGNORECASE),
    re.compile(r"Quota\s+exceeded", re.IGNORECASE),
    re.compile(r"Usage\s+limit\s+reached", re.IGNORECASE),
    re.compile(r"limit\s+reached\s+for\s+all.*models", re.IGNORECASE),
    re.compile(r"RESOURCE_EXHAUSTED"),
    re.compile(r"PERMISSION_DENIED.*VALIDATION_REQUIRED"),
    re.compile(r"rate\s*limit", re.IGNORECASE),
]


def _output(data: dict) -> None:  # type: ignore[type-arg]
    """Write JSON to stdout and exit."""
    json.dump(data, sys.stdout)
    sys.stdout.write("\n")
    sys.stdout.flush()


def is_quota_error(response: str) -> bool:
    """Check if a response string matches any quota error pattern."""
    return any(p.search(response) for p in QUOTA_ERROR_PATTERNS)


def _find_switcher() -> str:
    """Find the switcher main.py path."""
    # Try relative to this script's location
    hooks_dir = Path(__file__).resolve().parent
    # hooks/ is inside switcher/ package during dev,
    # or inside ~/.config/cli-switcher/hooks/ when installed
    candidates = [
        hooks_dir.parent.parent / "main.py",  # dev: repo root
        Path.home() / ".local" / "bin" / "switcher",  # installed
    ]
    for c in candidates:
        if c.exists():
            return str(c)
    return "switcher"  # Fall back to PATH lookup


def main() -> None:
    """AfterAgent hook entry point."""
    try:
        # Parse stdin
        input_data = json.load(sys.stdin)
        response = input_data.get("prompt_response", "")

        if not response or not isinstance(response, str):
            _output({})
            return

        # Load config to check if auto-rotate is enabled
        # Import here to avoid import errors when run standalone
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
        from switcher.config import load_config
        from switcher.state import (
            get_rotation_state,
            update_rotation_state,
        )

        config = load_config()
        if not config["auto_rotate"]["enabled"]:
            _output({})
            return

        # Not a quota error → reset retry count and exit
        if not is_quota_error(response):
            rot = get_rotation_state("gemini")
            if rot["retry_count"] > 0:
                update_rotation_state("gemini", retry_count=0, last_error=None)
            _output({})
            return

        # Quota error detected — attempt rotation
        max_retries = config["auto_rotate"]["max_retries"]
        rot = get_rotation_state("gemini")

        if rot["retry_count"] >= max_retries:
            update_rotation_state(
                "gemini", retry_count=0, last_error="Max retries reached"
            )
            _output({})
            return

        # Call switcher gemini next
        switcher_cmd = _find_switcher()
        result = subprocess.run(
            [sys.executable, switcher_cmd, "gemini", "next"],
            capture_output=True,
            text=True,
            timeout=8,
        )

        if result.returncode != 0:
            _output({})
            return

        # Get new active profile name
        from switcher.state import get_active_profile

        new_profile = get_active_profile("gemini") or "next account"

        # Increment retry count
        update_rotation_state("gemini", retry_count=rot["retry_count"] + 1)

        _output(
            {
                "decision": "retry",
                "systemMessage": (
                    f"\U0001f504 Quota exhausted — switched to "
                    f"{new_profile}. Retrying..."
                ),
            }
        )

    except Exception:
        # Never crash the parent CLI
        _output({})


if __name__ == "__main__":
    main()
