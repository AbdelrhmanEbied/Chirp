"""Password hashing and other application-level security primitives.

Argon2id is the default: it is memory-hard, which is what makes offline
cracking of a leaked hash expensive on GPUs. Parameters are deliberately modest
so that a login on a laptop stays fast; production should raise `memory_cost`
after measuring.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

_hasher = PasswordHasher(time_cost=2, memory_cost=64 * 1024, parallelism=2, hash_len=32)

MIN_PASSWORD_LENGTH = 10
MAX_PASSWORD_LENGTH = 200


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(password_hash: str) -> bool:
    """True when the stored hash used weaker parameters than the current ones."""
    try:
        return _hasher.check_needs_rehash(password_hash)
    except InvalidHashError:
        return True


def generate_opaque_token(num_bytes: int = 32) -> str:
    """Refresh tokens are random strings, not JWTs.

    A refresh token must be revocable the instant a user logs out, and a
    self-contained signed token cannot be revoked without a server-side
    lookup -- at which point it may as well be an opaque id.
    """
    return secrets.token_urlsafe(num_bytes)


def hash_token(token: str) -> str:
    """Store only the hash, so a database leak does not yield live sessions."""
    return hashlib.sha256(token.encode()).hexdigest()


def tokens_equal(left: str, right: str) -> bool:
    return hmac.compare_digest(left, right)
