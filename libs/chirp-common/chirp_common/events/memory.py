"""In-process event bus for tests.

Same interface as the Redis implementation, so event-handling tests exercise
the real handler code and the real envelope without a broker running.
"""

from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Sequence

from chirp_common.events.envelope import EventEnvelope, EventType


class InMemoryEventBus:
    def __init__(self, service_name: str = "test") -> None:
        self._service = service_name
        self.published: list[EventEnvelope] = []
        self.dead_lettered: list[tuple[EventEnvelope, str]] = []
        self._queues: dict[str, deque[tuple[str, EventEnvelope, int]]] = defaultdict(deque)
        self._counter = 0

    async def publish(self, event: EventEnvelope) -> None:
        await self.publish_many([event])

    async def publish_many(self, events: Sequence[EventEnvelope]) -> None:
        for event in events:
            self._counter += 1
            self.published.append(event)
            self._queues[event.type.value].append((str(self._counter), event, 1))

    async def dead_letter(self, event: EventEnvelope, reason: str) -> None:
        self.dead_lettered.append((event, reason))

    async def ensure_groups(self, consumer: str, types: Sequence[EventType]) -> None:
        return None

    async def read(
        self, consumer: str, instance: str, types: Sequence[EventType]
    ) -> list[tuple[str, str, EventEnvelope, int]]:
        batch: list[tuple[str, str, EventEnvelope, int]] = []
        for event_type in types:
            queue = self._queues[event_type.value]
            while queue:
                entry_id, event, attempt = queue.popleft()
                batch.append((event_type.value, entry_id, event, attempt))
        return batch

    async def ack(self, stream: str, consumer: str, entry_id: str) -> None:
        return None

    async def check(self) -> bool:
        return True

    async def close(self) -> None:
        return None

    def published_of(self, event_type: EventType) -> list[EventEnvelope]:
        return [e for e in self.published if e.type is event_type]
