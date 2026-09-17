from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from chirp_common.db.base import Base, TimestampMixin, ULIDPrimaryKeyMixin
from chirp_common.idempotency import ProcessedEvent  # noqa: F401
from chirp_common.ids import ULID_LENGTH


class Report(ULIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "reports"

    reporter_id: Mapped[str] = mapped_column(String(ULID_LENGTH), nullable=False, index=True)
    target_type: Mapped[str] = mapped_column(String(20), nullable=False)
    target_id: Mapped[str] = mapped_column(String(ULID_LENGTH), nullable=False, index=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    state: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    reviewed_by: Mapped[str | None] = mapped_column(String(ULID_LENGTH), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolution: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index("ix_reports_target", "target_type", "target_id"),
    )


class ModerationAction(ULIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "moderation_actions"

    admin_id: Mapped[str] = mapped_column(String(ULID_LENGTH), nullable=False, index=True)
    action_type: Mapped[str] = mapped_column(String(50), nullable=False)
    target_type: Mapped[str] = mapped_column(String(20), nullable=False)
    target_id: Mapped[str] = mapped_column(String(ULID_LENGTH), nullable=False, index=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False)


__all__ = ["ModerationAction", "ProcessedEvent", "Report"]
