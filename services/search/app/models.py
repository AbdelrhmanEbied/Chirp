from __future__ import annotations

from chirp_common.db.base import Base, TimestampMixin
from chirp_common.idempotency import ProcessedEvent  # noqa: F401
from chirp_common.ids import ULID_LENGTH
from sqlalchemy import DateTime, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column


class PostSearch(TimestampMixin, Base):
    __tablename__ = "post_search"

    id: Mapped[str] = mapped_column(String(ULID_LENGTH), primary_key=True)
    post_id: Mapped[str] = mapped_column(
        String(ULID_LENGTH), nullable=False, unique=True, index=True
    )
    author_id: Mapped[str] = mapped_column(String(ULID_LENGTH), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    created_at_index: Mapped[str] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index("ix_post_search_author", "author_id"),
        Index("ix_post_search_created", "created_at_index"),
    )


class HashtagUsage(TimestampMixin, Base):
    __tablename__ = "hashtag_usage"

    hashtag: Mapped[str] = mapped_column(String(100), primary_key=True)
    usage_count: Mapped[int] = mapped_column(nullable=False, default=0)


__all__ = ["HashtagUsage", "PostSearch", "ProcessedEvent"]
