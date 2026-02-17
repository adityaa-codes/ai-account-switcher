"""Keyring backend with automatic file fallback for headless systems."""

from __future__ import annotations

import logging
import os

from switcher.errors import KeyringError

logger = logging.getLogger("switcher.auth.keyring")

_KEYRING_AVAILABLE: bool | None = None


def detect_keyring_mode(force_mode: str = "auto") -> str:
    """Detect whether a real OS keyring is available.

    Args:
        force_mode: 'keyring', 'file', or 'auto'. If not 'auto', returns as-is.

    Returns:
        'keyring' or 'file'.
    """
    if force_mode in ("keyring", "file"):
        return force_mode

    global _KEYRING_AVAILABLE
    if _KEYRING_AVAILABLE is not None:
        return "keyring" if _KEYRING_AVAILABLE else "file"

    # Check for graphical session
    if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        logger.info("No graphical session detected — using file-only mode")
        _KEYRING_AVAILABLE = False
        return "file"

    try:
        import keyring
        from keyring.backends.fail import Keyring as FailKeyring

        backend = keyring.get_keyring()
        backend_name = type(backend).__name__

        if isinstance(backend, FailKeyring) or "Plaintext" in backend_name:
            logger.info(
                "No secure keyring backend found (%s) — using file mode",
                backend_name,
            )
            _KEYRING_AVAILABLE = False
            return "file"

        logger.info("Keyring backend: %s", backend_name)
        _KEYRING_AVAILABLE = True
        return "keyring"

    except Exception:
        logger.warning(
            "Keyring detection failed — falling back to file mode",
            exc_info=True,
        )
        _KEYRING_AVAILABLE = False
        return "file"


def keyring_read(service: str, key: str) -> str | None:
    """Read a value from the OS keyring.

    Args:
        service: Keyring service name.
        key: Keyring key/account name.

    Returns:
        The stored string, or None if not found.

    Raises:
        KeyringError: If the read operation fails.
    """
    try:
        import keyring

        value: str | None = keyring.get_password(service, key)
        return value
    except Exception as exc:
        raise KeyringError(f"Failed to read keyring ({service}/{key}): {exc}") from exc


def keyring_write(service: str, key: str, value: str) -> None:
    """Write a value to the OS keyring.

    Args:
        service: Keyring service name.
        key: Keyring key/account name.
        value: The string to store.

    Raises:
        KeyringError: If the write operation fails.
    """
    try:
        import keyring

        keyring.set_password(service, key, value)
    except Exception as exc:
        raise KeyringError(f"Failed to write keyring ({service}/{key}): {exc}") from exc


def keyring_delete(service: str, key: str) -> None:
    """Delete a keyring entry.

    Args:
        service: Keyring service name.
        key: Keyring key/account name.

    Raises:
        KeyringError: If the delete operation fails
            (missing entries are silently ignored).
    """
    try:
        import keyring

        keyring.delete_password(service, key)
    except keyring.errors.PasswordDeleteError:
        # Entry didn't exist — not an error
        pass
    except Exception as exc:
        raise KeyringError(
            f"Failed to delete keyring ({service}/{key}): {exc}"
        ) from exc
