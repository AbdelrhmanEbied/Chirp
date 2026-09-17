"""Consumer-side idempotency.

The bus guarantees at-least-once delivery, so every consumer must tolerate
seeing the same event twice: a redelivery after a crash, a retry after a
transient failure, or a claim of a stale pending entry.

Each consuming service owns a `processed_events` table. The handler and the
insert run in the same transaction, so "did the work" and "recorded that we
did the work" commit or roll back together. A duplicate is detected by the
primary key conflict, not by a read-then-write race.

Handlers that are naturally idempotent (an UPSERT keyed by the event's own
identifiers) may skip this and say so in a comment.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String, func, insert, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from chirp_common.db.base import Base
from chirp_common.ids import ULID_LENGTH


class ProcessedEvent(Base):
    """Ledger of event ids this service has already applied."""

    __tablename__ = "processed_events"

    event_id: Mapped[str] = mapped_column(String(ULID_LENGTH), primary_key=True)
    consumer: Mapped[str] = mapped_column(String(128), primary_key=True)
    event_type: Mapped[str] = mapped_column(String(128), nullable=False)
    processed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )


async def claim_event(
    session: AsyncSession, *, event_id: str, consumer: str, event_type: str
) -> bool:
    """Record this event as processed. Returns False if it already was.

    Must be called inside the same transaction as the handler's writes.
    """
    dialect = session.bind.dialect.name if session.bind is not None else "postgresql"
    if dialect == "postgresql":
        stmt = (
            pg_insert(ProcessedEvent)
            .values(event_id=event_id, consumer=consumer, event_type=event_type)
            .on_conflict_do_nothing(index_elements=["event_id", "consumer"])
            .returning(ProcessedEvent.event_id)
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none() is not None

    existing = await session.scalar(
        select(ProcessedEvent.event_id).where(
            ProcessedEvent.event_id == event_id, ProcessedEvent.consumer == consumer
        )
    )
    if existing is not None:
        return False
    await session.execute(
        insert(ProcessedEvent).values(
            event_id=event_id, consumer=consumer, event_type=event_type
        )
    )
    return True
