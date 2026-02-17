"""Exception hierarchy for CLI Switcher.

All switcher-specific exceptions inherit from SwitcherError, allowing
callers to catch the base class for generic error handling or specific
subclasses for targeted recovery.
"""

from __future__ import annotations


class SwitcherError(Exception):
    """Base exception for all switcher errors."""


class ProfileNotFoundError(SwitcherError):
    """Requested profile does not exist."""


class ProfileCorruptError(SwitcherError):
    """Profile directory exists but credentials are missing or invalid."""


class AuthError(SwitcherError):
    """Authentication operation failed."""


class KeyringError(AuthError):
    """Keyring read/write failed."""


class TokenExpiredError(AuthError):
    """Token refresh failed — re-login needed."""


class ConfigError(SwitcherError):
    """Configuration file is missing or invalid."""


class HookError(SwitcherError):
    """Hook execution failed."""
