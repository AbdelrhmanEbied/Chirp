
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import DateTime, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from chirp_common.db.base import Base
from chirp_common.idempotency import ProcessedEvent  # noqa: F401


class FeedEntry(Base):
    __tablename__ = "feed_entries"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(26), index=True)
    post_id: Mapped[str] = mapped_column(String(26), index=True)
    author_id: Mapped[str] = mapped_column(String(26), index=True)
    text: Mapped[str] = mapped_column(Text)
    likes_count: Mapped[int] = mapped_column(default=0)
    reposts_count: Mapped[int] = mapped_column(default=0)
    replies_count: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    inserted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    __table_args__ = (
        Index("ix_feed_entries_user_created", "user_id", "created_at"),
    )
