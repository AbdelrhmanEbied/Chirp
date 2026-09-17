from __future__ import annotations

from sqlalchemy import Boolean, DateTime, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from chirp_common.db.base import Base, TimestampMixin, ULIDPrimaryKeyMixin
from chirp_common.idempotency import ProcessedEvent  # noqa: F401
from chirp_common.ids import ULID_LENGTH


class Notification(ULIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "notifications"

    recipient_id: Mapped[str] = mapped_column(String(ULID_LENGTH), nullable=False, index=True)
    actor_id: Mapped[str] = mapped_column(String(ULID_LENGTH), nullable=False)
    notification_type: Mapped[str] = mapped_column(String(50), nullable=False)
    subject_id: Mapped[str] = mapped_column(String(ULID_LENGTH), nullable=False)
    is_read: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    __table_args__ = (
        Index("ix_notifications_recipient_read", "recipient_id", "is_read"),
        Index("ix_notifications_recipient_created", "recipient_id", "created_at"),
    )


__all__ = ["Notification", "ProcessedEvent"]
