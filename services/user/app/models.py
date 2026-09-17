"""Tables owned by the user service: public profiles and username history.

`id` is the same value as the auth service's account id. There is no foreign
key to it: the row lives in another database owned by another service, and a
constraint across that boundary would couple their deployments and their
schemas. The invariant is maintained by the registration handshake instead.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from chirp_common.db.base import (
    Base,
    SoftDeleteMixin,
    TimestampMixin,
    ULIDPrimaryKeyMixin,
)
from chirp_common.idempotency import ProcessedEvent  # noqa: F401 - registered on metadata
from chirp_common.ids import ULID_LENGTH


class UserProfile(TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "user_profiles"

    id: Mapped[str] = mapped_column(String(ULID_LENGTH), primary_key=True)

    # Stored lowercase; display casing is not preserved because usernames are
    # compared case-insensitively everywhere and storing both invites drift.
    username: Mapped[str] = mapped_column(String(20), nullable=False, unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(50), nullable=False)
    bio: Mapped[str | None] = mapped_column(Text, nullable=True)
    location: Mapped[str | None] = mapped_column(String(100), nullable=True)
    website: Mapped[str | None] = mapped_column(String(200), nullable=True)

    # Media ids, not URLs: the media service owns where bytes actually live,
    # so moving from local disk to S3+CDN does not rewrite user rows.
    avatar_media_id: Mapped[str | None] = mapped_column(String(ULID_LENGTH), nullable=True)
    banner_media_id: Mapped[str | None] = mapped_column(String(ULID_LENGTH), nullable=True)

    username_changed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Denormalised counters, updated from events. They are an optimisation,
    # not a source of truth: the authoritative counts are COUNT(*) queries in
    # the graph and post services, and `scripts/reconcile_counters.py` can
    # rebuild them. Drift is possible and acceptable; a wrong follower count
    # is not a correctness bug in the way a wrong follow edge would be.
    followers_count: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    following_count: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    posts_count: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)

    __table_args__ = (
        Index("ix_user_profiles_display_name", "display_name"),
        Index("ix_user_profiles_username_active", "username", "deleted_at"),
    )


class UsernameHistory(ULIDPrimaryKeyMixin, TimestampMixin, Base):
    """Previous usernames, kept so freed handles cannot be re-registered
    immediately and impersonate the previous owner."""

    __tablename__ = "username_history"

    user_id: Mapped[str] = mapped_column(String(ULID_LENGTH), nullable=False, index=True)
    username: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    released_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


__all__ = ["ProcessedEvent", "UserProfile", "UsernameHistory"]
