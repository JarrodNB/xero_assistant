"""Purpose: Check and hash the single interviewer password.

Public API:
- hash_password
- password_matches
- credentials_match
"""

import secrets

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from app.config import Settings

_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    """Return an argon2 hash for a plaintext password."""
    return _hasher.hash(password)


def password_matches(password_hash: str, password: str) -> bool:
    """Return whether the password matches the stored hash."""
    try:
        return _hasher.verify(password_hash, password)
    except VerifyMismatchError:
        return False
    except Exception:
        return False


def credentials_match(username: str, password: str, settings: Settings) -> bool:
    """Return whether the username and password match the shared account."""
    password_ok = password_matches(settings.app_password_hash, password)
    username_ok = secrets.compare_digest(username, settings.app_username)
    return password_ok and username_ok
