from __future__ import annotations

import os
import time

_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
_DECODE = {c: i for i, c in enumerate(_ALPHABET)}
ULID_LENGTH = 26

def new_ulid(timestamp_ms: int | None = None) -> str:
    ts = int(time.time() * 1000) if timestamp_ms is None else timestamp_ms
    value = (ts << 80) | int.from_bytes(os.urandom(10), "big")
    return _encode(value, ULID_LENGTH)

def ulid_timestamp_ms(value: str) -> int:
    return _decode(value) >> 80

def is_ulid(value: str) -> bool:
    if len(value) != ULID_LENGTH:
        return False
    return all(c in _DECODE for c in value.upper())

def _encode(value: int, length: int) -> str:
    chars = []
    for _ in range(length):
        chars.append(_ALPHABET[value & 0x1F])
        value >>= 5
    return "".join(reversed(chars))

def _decode(value: str) -> int:
    result = 0
    for char in value.upper():
        try:
            result = (result << 5) | _DECODE[char]
        except KeyError as exc:# pragma: no cover - defensive
            raise ValueError(f"invalid ULID character: {char!r}") from exc
    return result
