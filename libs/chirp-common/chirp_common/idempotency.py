from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String, func, insert, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from chirp_common.db.base import Base
from chirp_common.ids import ULID_LENGTH

class ProcessedEvent(Base):

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
