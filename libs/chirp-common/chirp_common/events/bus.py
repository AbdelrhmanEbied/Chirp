"""Broker-agnostic publish/subscribe interface.

Application code depends only on this. Redis Streams is the local development
implementation; replacing it with SNS/SQS or Kafka means writing one new class
here and changing `EVENT_BUS_BACKEND`, with no change to any service.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from typing import Protocol, runtime_checkable

from chirp_common.events.envelope import EventEnvelope, EventType

EventHandler = Callable[[EventEnvelope], Awaitable[None]]


@runtime_checkable
class EventBus(Protocol):
    async def publish(self, event: EventEnvelope) -> None:
        """Publish one event. Must not raise for transient broker errors
        without the caller having a way to notice -- see the outbox note in
        docs/events.md for the delivery guarantee this gives."""
        ...

    async def publish_many(self, events: Sequence[EventEnvelope]) -> None: ...

    async def dead_letter(self, event: EventEnvelope, reason: str) -> None:
        """Park an event that has exhausted its retries."""
        ...

    async def ensure_groups(self, consumer: str, types: Sequence[EventType]) -> None:
        """Create whatever the broker needs before consuming (idempotent)."""
        ...

    async def read(
        self, consumer: str, instance: str, types: Sequence[EventType]
    ) -> list[tuple[str, str, EventEnvelope, int]]:
        """Return `(stream, entry_id, event, delivery_attempt)` tuples."""
        ...

    async def ack(self, stream: str, consumer: str, entry_id: str) -> None: ...

    async def close(self) -> None: ...
