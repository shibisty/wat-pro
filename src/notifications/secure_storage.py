"""
Stores the SMTP password via the system credential store (Windows
Credential Manager / macOS Keychain / Secret Service on Linux) through
the keyring package — the password never ends up in the DB or
settings.ini in plain text.
"""

from typing import Optional

import keyring
import keyring.errors

SERVICE_NAME = "src_smtp"


class SecureStorageUnavailable(Exception):
    """The system password store is unavailable on this machine."""


def save_password(username: str, password: str):
    try:
        keyring.set_password(SERVICE_NAME, username, password)
    except keyring.errors.KeyringError as e:
        raise SecureStorageUnavailable(str(e)) from e


def get_password(username: str) -> Optional[str]:
    try:
        return keyring.get_password(SERVICE_NAME, username)
    except keyring.errors.KeyringError as e:
        raise SecureStorageUnavailable(str(e)) from e


def delete_password(username: str):
    try:
        keyring.delete_password(SERVICE_NAME, username)
    except keyring.errors.PasswordDeleteError:
        pass
    except keyring.errors.KeyringError as e:
        raise SecureStorageUnavailable(str(e)) from e
