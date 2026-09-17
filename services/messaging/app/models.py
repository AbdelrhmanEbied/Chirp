from __future__ import annotations

from sqlalchemy import Boolean, DateTime, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from chirp_common.db.base import Base, TimestampMixin, ULIDPrimaryKeyMixin
from chirp_common.idempotency import ProcessedEvent  # noqa: F401
from chirp_common.ids import ULID_LENGTH


class Conversation(ULIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "conversations"

    title: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at_index: Mapped[str] = mapped_column(DateTime(timezone=True), nullable=False)


class ConversationParticipant(TimestampMixin, Base):
    __tablename__ = "conversation_participants"

    conversation_id: Mapped[str] = mapped_column(String(ULID_LENGTH), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(ULID_LENGTH), primary_key=True)
    last_read_at: Mapped[str | None] = mapped_column(DateTime(timezone=True), nullable=True)
    joined_at: Mapped[str] = mapped_column(DateTime(timezone=True), nullable=False)


class Message(ULIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "messages"

    conversation_id: Mapped[str] = mapped_column(String(ULID_LENGTH), nullable=False, index=True)
    sender_id: Mapped[str] = mapped_column(String(ULID_LENGTH), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    deleted_at: Mapped[str | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_messages_conversation_created", "conversation_id", "created_at"),
    )
