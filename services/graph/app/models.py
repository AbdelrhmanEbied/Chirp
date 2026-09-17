"""Tables owned by the graph service: follow, block and mute edges.

Cross-service references are stored as plain id strings with no foreign key,
because the referenced row lives in a different database.
"""

from __future__ import annotations

from sqlalchemy import Index, String
from sqlalchemy.orm import Mapped, mapped_column

from chirp_common.db.base import Base, TimestampMixin
from chirp_common.idempotency import ProcessedEvent  # noqa: F401 - registered on metadata
from chirp_common.ids import ULID_LENGTH


class Follow(TimestampMixin, Base):
    __tablename__ = "follows"

    follower_id: Mapped[str] = mapped_column(String(ULID_LENGTH), primary_key=True)
    followee_id: Mapped[str] = mapped_column(String(ULID_LENGTH), primary_key=True)

    __table_args__ = (
        Index("ix_follows_followee_id", "followee_id"),
        Index("ix_follows_created_at", "created_at"),
    )


class Block(TimestampMixin, Base):
    __tablename__ = "blocks"

    blocker_id: Mapped[str] = mapped_column(String(ULID_LENGTH), primary_key=True)
    blocked_id: Mapped[str] = mapped_column(String(ULID_LENGTH), primary_key=True)

    __table_args__ = (
        Index("ix_blocks_blocked_id", "blocked_id"),
        Index("ix_blocks_created_at", "created_at"),
    )


class Mute(TimestampMixin, Base):
    __tablename__ = "mutes"

    user_id: Mapped[str] = mapped_column(String(ULID_LENGTH), primary_key=True)
    muted_id: Mapped[str] = mapped_column(String(ULID_LENGTH), primary_key=True)

    __table_args__ = (
        Index("ix_mutes_muted_id", "muted_id"),
        Index("ix_mutes_created_at", "created_at"),
    )


__all__ = ["Block", "Follow", "Mute", "ProcessedEvent"]
