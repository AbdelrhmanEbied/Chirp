"""Cross-service event flow tests.

These tests verify that events are produced and consumed correctly
across service boundaries, using in-memory buses and SQLite databases.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from chirp_common.db.base import Base
from chirp_common.db.session import Database
from chirp_common.events.memory import InMemoryEventBus
from chirp_common.events.envelope import EventEnvelope, EventType
from chirp_common.idempotency import claim_event
from chirp_common.testing.factories import make_event

import os

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "sqlite+aiosqlite:///:memory:")


@pytest_asyncio.fixture
async def db():
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
    engine = create_async_engine(TEST_DATABASE_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    async with sessionmaker() as session:
        yield session
    await engine.dispose()


async def test_idempotent_event_processing(db) -> None:
    """Processing the same event twice should be idempotent."""
    from chirp_common.idempotency import ProcessedEvent

    event = make_event(EventType.POST_CREATED, subject_id="post-01")

    # First claim should succeed
    first = await claim_event(
        db, event_id=event.id, consumer="test-consumer", event_type=event.type.value,
    )
    assert first is True
    await db.commit()

    # Second claim should be rejected
    second = await claim_event(
        db, event_id=event.id, consumer="test-consumer", event_type=event.type.value,
    )
    assert second is False


async def test_different_consumers_can_process_same_event(db) -> None:
    """Different consumers can independently process the same event."""
    event = make_event(EventType.POST_CREATED, subject_id="post-01")

    first = await claim_event(
        db, event_id=event.id, consumer="consumer-a", event_type=event.type.value,
    )
    assert first is True

    second = await claim_event(
        db, event_id=event.id, consumer="consumer-b", event_type=event.type.value,
    )
    assert second is True
    await db.commit()


async def test_event_envelope_serialization() -> None:
    """Events can be serialized and deserialized without data loss."""
    original = EventEnvelope.create(
        type=EventType.POST_CREATED,
        producer="post-service",
        subject_id="post-01",
        actor_id="user-01",
        payload={"text": "Hello!", "hashtags": ["chirp"], "mentions": ["alice"]},
    )

    json_str = original.model_dump_json()
    restored = EventEnvelope.model_validate_json(json_str)

    assert restored.id == original.id
    assert restored.type == original.type
    assert restored.subject_id == original.subject_id
    assert restored.payload == original.payload
