"""Encrypt local integration secrets with the provider credential key."""

import os
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

from ...config import settings


def _read_or_create_key(path: Path) -> bytes:
    """Return a private Fernet key, creating it atomically with mode 0600."""
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        key = path.read_bytes()
    else:
        try:
            key = Fernet.generate_key()
            os.write(descriptor, key)
        finally:
            os.close(descriptor)
    try:
        os.chmod(path, 0o600)
        Fernet(key)
    except (OSError, ValueError) as error:
        raise RuntimeError(f"Invalid provider encryption key: {path}") from error
    return key


def _fernet() -> Fernet:
    return Fernet(_read_or_create_key(settings.provider_key_path))


def encrypt_secret(value: str | None) -> str | None:
    """Encrypt one optional plaintext secret."""
    return _fernet().encrypt(value.encode()).decode() if value is not None else None


def decrypt_secret(ciphertext: str | None) -> str | None:
    """Decrypt one optional stored secret."""
    if ciphertext is None:
        return None
    try:
        return _fernet().decrypt(ciphertext.encode()).decode()
    except InvalidToken as error:
        raise RuntimeError("Stored secret cannot be decrypted with the local key") from error
