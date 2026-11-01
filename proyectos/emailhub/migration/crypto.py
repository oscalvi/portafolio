"""Symmetric encryption for IMAP app passwords stored in the database."""
from __future__ import annotations

from django.conf import settings
from cryptography.fernet import Fernet

_GEN_HINT = (
    'python -c "from cryptography.fernet import Fernet; '
    'print(Fernet.generate_key().decode())"'
)


def _fernet() -> Fernet:
    key = settings.FIELD_ENCRYPTION_KEY
    if not key:
        raise RuntimeError(
            f"FIELD_ENCRYPTION_KEY is not set. Generate one with:\n  {_GEN_HINT}"
        )
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt(token: str) -> str:
    return _fernet().decrypt(token.encode()).decode()
