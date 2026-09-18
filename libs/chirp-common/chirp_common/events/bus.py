from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from typing import Protocol, runtime_checkable

from chirp_common.events.envelope import EventEnvelope, EventType

EventHandler = Callable[[EventEnvelope], Awaitable[None]]

@runtime_checkable
class EventBus(Protocol):
    async def publish(self, event: EventEnvelope) -> None:
        ...

    async def publish_many(self, events: Sequence[EventEnvelope]) -> None: ...

    async def dead_letter(self, event: EventEnvelope, reason: str) -> None:
        ...

    async def ensure_groups(self, consumer: str, types: Sequence[EventType]) -> None:
        ...

    async def read(
        self, consumer: str, instance: str, types: Sequence[EventType]
    ) -> list[tuple[str, str, EventEnvelope, int]]:
        ...

    async def ack(self, stream: str, consumer: str, entry_id: str) -> None: ...

    async def close(self) -> None: ...
