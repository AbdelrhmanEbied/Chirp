
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

    username: Mapped[str] = mapped_column(String(20), nullable=False, unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(50), nullable=False)
    bio: Mapped[str | None] = mapped_column(Text, nullable=True)
    location: Mapped[str | None] = mapped_column(String(100), nullable=True)
    website: Mapped[str | None] = mapped_column(String(200), nullable=True)

    avatar_media_id: Mapped[str | None] = mapped_column(String(ULID_LENGTH), nullable=True)
    banner_media_id: Mapped[str | None] = mapped_column(String(ULID_LENGTH), nullable=True)

    username_changed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    followers_count: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    following_count: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    posts_count: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)

    __table_args__ = (
        Index("ix_user_profiles_display_name", "display_name"),
        Index("ix_user_profiles_username_active", "username", "deleted_at"),
    )


class UsernameHistory(ULIDPrimaryKeyMixin, TimestampMixin, Base):

    __tablename__ = "username_history"

    user_id: Mapped[str] = mapped_column(String(ULID_LENGTH), nullable=False, index=True)
    username: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    released_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


__all__ = ["ProcessedEvent", "UserProfile", "UsernameHistory"]
