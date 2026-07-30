"""
Хранение пароля от SMTP через системное хранилище (Windows Credential
Manager / macOS Keychain / Secret Service на Linux) через пакет keyring —
пароль никогда не попадает в БД или settings.ini в открытом виде.
"""

from typing import Optional

import keyring
import keyring.errors

SERVICE_NAME = "qt_test_tool_smtp"


class SecureStorageUnavailable(Exception):
    """Системное хранилище паролей недоступно на этой машине."""


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
