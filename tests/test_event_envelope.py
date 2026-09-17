"""Tests for the event envelope and bus."""

from __future__ import annotations

import pytest
from chirp_common.events.envelope import EventEnvelope, EventType
from chirp_common.events.memory import InMemoryEventBus
from chirp_common.ids import new_ulid


class TestEventEnvelope:
    def test_create_event(self) -> None:
        event = EventEnvelope.create(
            type=EventType.POST_CREATED,
            producer="test-service",
            subject_id="post-01",
            actor_id="user-01",
            payload={"text": "hello"},
        )
        assert event.type == EventType.POST_CREATED
        assert event.producer == "test-service"
        assert event.subject_id == "post-01"
        assert event.actor_id == "user-01"
        assert event.payload == {"text": "hello"}
        assert len(event.id) == 26

    def test_stream_name(self) -> None:
        event = EventEnvelope.create(
            type=EventType.POST_CREATED,
            producer="test",
            subject_id="x",
        )
        assert event.stream_name("chirp.events") == "chirp.events.post.created"

    def test_event_types_are_all_string(self) -> None:
        for et in EventType:
            assert isinstance(et.value, str)
            assert "." in et.value


class TestInMemoryEventBus:
    @pytest.fixture
    def bus(self) -> InMemoryEventBus:
        return InMemoryEventBus("test")

    async def test_publish_and_read(self, bus: InMemoryEventBus) -> None:
        event = EventEnvelope.create(
            type=EventType.POST_CREATED,
            producer="test",
            subject_id="post-01",
        )
        await bus.publish(event)

        results = await bus.read("consumer-1", "instance-1", [EventType.POST_CREATED])
        assert len(results) == 1
        assert results[0][2].subject_id == "post-01"

    async def test_published_of(self, bus: InMemoryEventBus) -> None:
        await bus.publish(EventEnvelope.create(
            type=EventType.POST_CREATED, producer="test", subject_id="p1",
        ))
        await bus.publish(EventEnvelope.create(
            type=EventType.POST_LIKED, producer="test", subject_id="p1",
        ))

        created = bus.published_of(EventType.POST_CREATED)
        liked = bus.published_of(EventType.POST_LIKED)
        assert len(created) == 1
        assert len(liked) == 1

    async def test_dead_letter(self, bus: InMemoryEventBus) -> None:
        event = EventEnvelope.create(
            type=EventType.POST_CREATED, producer="test", subject_id="p1",
        )
        await bus.dead_letter(event, "test reason")
        assert len(bus.dead_lettered) == 1
        assert bus.dead_lettered[0][1] == "test reason"

    async def test_publish_many(self, bus: InMemoryEventBus) -> None:
        events = [
            EventEnvelope.create(type=EventType.POST_CREATED, producer="test", subject_id=f"p{i}")
            for i in range(5)
        ]
        await bus.publish_many(events)
        assert len(bus.published) == 5
