from __future__ import annotations

from chirp_common.db.base import Base, TimestampMixin, ULIDPrimaryKeyMixin
from chirp_common.idempotency import ProcessedEvent  # noqa: F401
from chirp_common.ids import ULID_LENGTH
from sqlalchemy import BigInteger, Index, String
from sqlalchemy.orm import Mapped, mapped_column


class Media(ULIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "media"

    owner_id: Mapped[str] = mapped_column(String(ULID_LENGTH), nullable=False, index=True)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    file_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    storage_key: Mapped[str] = mapped_column(String(500), nullable=False)
    state: Mapped[str] = mapped_column(String(20), nullable=False, default="ready")
    width: Mapped[int | None] = mapped_column(nullable=True)
    height: Mapped[int | None] = mapped_column(nullable=True)

    __table_args__ = (
        Index("ix_media_owner_created", "owner_id", "created_at"),
    )


__all__ = ["Media", "ProcessedEvent"]
