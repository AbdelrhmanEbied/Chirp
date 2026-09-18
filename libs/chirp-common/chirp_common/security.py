from __future__ import annotations

import hashlib
import hmac
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

_hasher = PasswordHasher(time_cost=3, memory_cost=256 * 1024, parallelism=4, hash_len=32)

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
    try:
        return _hasher.check_needs_rehash(password_hash)
    except InvalidHashError:
        return True

def generate_opaque_token(num_bytes: int = 32) -> str:
    return secrets.token_urlsafe(num_bytes)

def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()

def tokens_equal(left: str, right: str) -> bool:
    return hmac.compare_digest(left, right)
