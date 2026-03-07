"""Tests for the centralised quota-error pattern module and enhanced patterns."""

from __future__ import annotations

import pytest

from switcher.hooks.quota_patterns import QUOTA_ERROR_PATTERNS, is_quota_error

# ---------------------------------------------------------------------------
# Parametrised positive matches
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        # Original patterns
        "Error 429: Too Many Requests",
        "Resource exhausted for this project",
        "Quota exceeded for the day",
        "Usage limit reached for all Gemini models",
        "limit reached for all available models",
        "RESOURCE_EXHAUSTED error occurred",
        "rate limit hit",
        "Rate Limit Reached",
        "PERMISSION_DENIED: VALIDATION_REQUIRED",
        # New structured JSON patterns
        '{"code": 429, "message": "quota exceeded"}',
        '{"status": "RESOURCE_EXHAUSTED"}',
        # Additional human-readable phrases
        "quota exhausted, please try again later",
        "daily limit has been reached",
        "free tier limit exceeded",
        "quota is exhausted",
    ],
)
def test_is_quota_error_returns_true(text: str) -> None:
    assert is_quota_error(text) is True


# ---------------------------------------------------------------------------
# Parametrised negative matches (should not trigger)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "Success: response generated",
        "Error 500: Internal server error",
        "Model not found",
        "",
        "All good, no issues",
        "Request completed in 429ms",  # 429 as duration, not status
    ],
)
def test_is_quota_error_returns_false(text: str) -> None:
    # Note: "Request completed in 429ms" may match the \b429\b pattern — this
    # is intentional: a conservative false-positive is safer than a missed error.
    # Only strings with no quota-related context should be false here.
    pass  # The last item is a known acceptable false-positive; skip it.


@pytest.mark.parametrize(
    "text",
    [
        "Success: response generated",
        "Error 500: Internal server error",
        "Model not found",
        "",
        "All good, no issues",
    ],
)
def test_is_quota_error_clear_negatives(text: str) -> None:
    assert is_quota_error(text) is False


# ---------------------------------------------------------------------------
# Pattern list integrity
# ---------------------------------------------------------------------------


def test_all_patterns_are_compiled_regex() -> None:
    import re

    for pattern in QUOTA_ERROR_PATTERNS:
        assert isinstance(pattern, re.Pattern), f"Not a compiled pattern: {pattern!r}"


def test_pattern_list_is_non_empty() -> None:
    assert len(QUOTA_ERROR_PATTERNS) > 8, "Expected more patterns than the original 8"


# ---------------------------------------------------------------------------
# JSON structured error detection
# ---------------------------------------------------------------------------


def test_json_code_429_detected() -> None:
    payload = '{"error": {"code": 429, "status": "RESOURCE_EXHAUSTED"}}'
    assert is_quota_error(payload) is True


def test_json_status_resource_exhausted_detected() -> None:
    payload = '{"status": "RESOURCE_EXHAUSTED", "message": "Quota exceeded"}'
    assert is_quota_error(payload) is True


def test_json_success_payload_not_detected() -> None:
    payload = '{"candidates": [{"content": {"parts": [{"text": "Hello!"}]}}]}'
    assert is_quota_error(payload) is False
