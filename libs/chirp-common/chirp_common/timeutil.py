"""Timezone helpers.

Every timestamp in Chirp is stored as `timestamptz` and handled as aware UTC.
`ensure_utc` exists because drivers differ: PostgreSQL returns aware datetimes,
while SQLite (used by the fast unit suite) returns naive ones. Comparing the
two raises `TypeError`, so values read from the database are normalised at the
boundary rather than defensively at every comparison.
"""

from __future__ import annotations

from datetime import UTC, datetime


def utcnow() -> datetime:
    return datetime.now(UTC)


def ensure_utc(value: datetime) -> datetime:
    """Attach UTC to a naive datetime; convert an aware one."""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
