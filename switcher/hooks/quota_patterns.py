"""Centralised quota-error detection patterns shared by both Gemini hooks."""

from __future__ import annotations

import re

# Patterns matched against the string form of a Gemini prompt_response.
# Covers both human-readable messages and structured JSON error payloads.
QUOTA_ERROR_PATTERNS: list[re.Pattern[str]] = [
    # HTTP 429 status code (bare number or inside JSON "code" field)
    re.compile(r"\b429\b", re.IGNORECASE),
    re.compile(r'"code"\s*:\s*429'),
    # gRPC / Google API error status
    re.compile(r"RESOURCE_EXHAUSTED"),
    re.compile(r'"status"\s*:\s*"RESOURCE_EXHAUSTED"'),
    # Human-readable quota messages
    re.compile(r"Resource\s+exhausted", re.IGNORECASE),
    re.compile(r"Quota\s+exceeded", re.IGNORECASE),
    re.compile(r"quota.*exhausted", re.IGNORECASE),
    re.compile(r"Usage\s+limit\s+reached", re.IGNORECASE),
    re.compile(r"limit\s+reached\s+for\s+all.*models", re.IGNORECASE),
    re.compile(r"free\s+tier.*limit", re.IGNORECASE),
    re.compile(r"daily.*limit", re.IGNORECASE),
    # Rate limiting
    re.compile(r"rate\s*limit", re.IGNORECASE),
    # OAuth / validation gate sometimes seen before quota swap
    re.compile(r"PERMISSION_DENIED.*VALIDATION_REQUIRED"),
]


def is_quota_error(text: str) -> bool:
    """Return True if *text* matches any known quota-exhaustion pattern.

    Args:
        text: Response string to check (may be plain text or serialised JSON).

    Returns:
        True if a quota error is detected, False otherwise.
    """
    return any(p.search(text) for p in QUOTA_ERROR_PATTERNS)
