"""
Symmetric encryption helpers for secrets (Hoyoverse cookies) stored in MongoDB.

Uses Fernet (AES-128-CBC + HMAC-SHA256, from the `cryptography` package) with a
single key loaded from the ENCRYPTION_KEY environment variable.
"""

import os

from cryptography.fernet import Fernet, InvalidToken
from dotenv import load_dotenv

load_dotenv()

_ENCRYPTION_KEY = os.environ["ENCRYPTION_KEY"]

try:
    _fernet = Fernet(_ENCRYPTION_KEY.encode())
except (ValueError, TypeError) as e:
    raise ValueError(
        "ENCRYPTION_KEY is not a valid Fernet key. Generate one with:\n"
        '  python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"'
    ) from e


def encrypt_str(plaintext: str) -> str:
    """Encrypt a string, returning a urlsafe-base64 ciphertext token."""
    return _fernet.encrypt(plaintext.encode()).decode()


def decrypt_str(token: str) -> str:
    """Decrypt a ciphertext token produced by encrypt_str."""
    try:
        return _fernet.decrypt(token.encode()).decode()
    except InvalidToken as e:
        raise ValueError(
            "Could not decrypt value -- wrong ENCRYPTION_KEY, corrupted data, "
            "or a not-yet-migrated plaintext value."
        ) from e