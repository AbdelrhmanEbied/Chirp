"""Tables owned by the post service.

Posts are soft-deleted because replies and timeline entries reference them.
Likes, reposts and bookmarks are hard-deleted: nothing else references them.
"""

from __future__ import annotations

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from chirp_common.db.base import Base, SoftDeleteMixin, TimestampMixin, ULIDPrimaryKeyMixin
from chirp_common.idempotency import ProcessedEvent  # noqa: F401
from chirp_common.ids import ULID_LENGTH


class Post(ULIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "posts"

    author_id: Mapped[str] = mapped_column(String(ULID_LENGTH), nullable=False, index=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    reply_to_id: Mapped[str | None] = mapped_column(String(ULID_LENGTH), nullable=True, index=True)
    quote_of_id: Mapped[str | None] = mapped_column(String(ULID_LENGTH), nullable=True)
    media_ids: Mapped[str | None] = mapped_column(Text, nullable=True)

    likes_count: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    reposts_count: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    replies_count: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    quotes_count: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)

    __table_args__ = (
        Index("ix_posts_author_created", "author_id", "created_at"),
        Index("ix_posts_reply_to", "reply_to_id"),
    )


class Like(TimestampMixin, Base):
    __tablename__ = "likes"

    user_id: Mapped[str] = mapped_column(String(ULID_LENGTH), primary_key=True)
    post_id: Mapped[str] = mapped_column(String(ULID_LENGTH), primary_key=True, index=True)
    post_author_id: Mapped[str] = mapped_column(String(ULID_LENGTH), nullable=False)

    __table_args__ = (
        Index("ix_likes_post", "post_id"),
    )


class Repost(TimestampMixin, Base):
    __tablename__ = "reposts"

    user_id: Mapped[str] = mapped_column(String(ULID_LENGTH), primary_key=True)
    post_id: Mapped[str] = mapped_column(String(ULID_LENGTH), primary_key=True, index=True)
    post_author_id: Mapped[str] = mapped_column(String(ULID_LENGTH), nullable=False)


class Bookmark(TimestampMixin, Base):
    __tablename__ = "bookmarks"

    user_id: Mapped[str] = mapped_column(String(ULID_LENGTH), primary_key=True)
    post_id: Mapped[str] = mapped_column(String(ULID_LENGTH), primary_key=True, index=True)

    __table_args__ = (
        Index("ix_bookmarks_user_created", "user_id", "created_at"),
    )


__all__ = ["Bookmark", "Like", "Post", "ProcessedEvent", "Repost"]
