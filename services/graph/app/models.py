
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
    )


class Block(TimestampMixin, Base):
    __tablename__ = "blocks"

    blocker_id: Mapped[str] = mapped_column(String(ULID_LENGTH), primary_key=True)
    blocked_id: Mapped[str] = mapped_column(String(ULID_LENGTH), primary_key=True)

    __table_args__ = (
        Index("ix_blocks_blocked_id", "blocked_id"),
    )


class Mute(TimestampMixin, Base):
    __tablename__ = "mutes"

    user_id: Mapped[str] = mapped_column(String(ULID_LENGTH), primary_key=True)
    muted_id: Mapped[str] = mapped_column(String(ULID_LENGTH), primary_key=True)

    __table_args__ = (
        Index("ix_mutes_muted_id", "muted_id"),
    )


__all__ = ["Block", "Follow", "Mute", "ProcessedEvent"]
