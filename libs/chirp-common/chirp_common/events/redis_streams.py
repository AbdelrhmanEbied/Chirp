from __future__ import annotations

import logging
from collections.abc import Sequence

import redis.asyncio as redis
from redis.exceptions import RedisError, ResponseError

from chirp_common.config import EventBusSettings
from chirp_common.errors import DependencyError
from chirp_common.events.envelope import EventEnvelope, EventType
from chirp_common.metrics import event_queue_depth, events_published_total

log = logging.getLogger(__name__)

DLQ_SUFFIX = "dlq"

class RedisStreamsEventBus:
    def __init__(self, settings: EventBusSettings, *, service_name: str) -> None:
        self._settings = settings
        self._service = service_name
        self._client = redis.from_url(
            settings.event_bus_url, decode_responses=True, socket_timeout=5, socket_connect_timeout=2, max_connections=20,
        )

    async def publish(self, event: EventEnvelope) -> None:
        await self.publish_many([event])

    async def publish_many(self, events: Sequence[EventEnvelope]) -> None:
        if not events:
            return
        try:
            async with self._client.pipeline(transaction=False) as pipe:
                for event in events:
                    pipe.xadd(
                        event.stream_name(self._settings.event_stream_prefix),
                        {"envelope": event.model_dump_json()},
                        maxlen=self._settings.event_max_stream_length,
                        approximate=True,
                    )
                await pipe.execute()
        except RedisError as exc:
            log.error(
                "event publish failed",
                extra={"count": len(events), "error": str(exc)},
            )
            raise DependencyError("Event bus is unavailable.") from exc

        for event in events:
            events_published_total.labels(self._service, event.type.value).inc()
            log.info(
                "event published",
                extra={"event_id": event.id, "event_type": event.type.value},
            )

    async def dead_letter(self, event: EventEnvelope, reason: str) -> None:
        stream = f"{self._settings.event_stream_prefix}.{DLQ_SUFFIX}"
        try:
            await self._client.xadd(
                stream,
                {
                    "envelope": event.model_dump_json(),
                    "reason": reason,
                    "consumer": self._service,
                },
                maxlen=self._settings.event_max_stream_length,
                approximate=True,
            )
        except RedisError as exc:
            log.error(
                "dead letter write failed",
                extra={"event_id": event.id, "error": str(exc)},
            )
            return
        log.warning(
            "event dead lettered",
            extra={"event_id": event.id, "event_type": event.type.value, "reason": reason},
        )

    def _stream(self, event_type: EventType) -> str:
        return f"{self._settings.event_stream_prefix}.{event_type.value}"

    async def ensure_groups(self, consumer: str, types: Sequence[EventType]) -> None:
        for event_type in types:
            stream = self._stream(event_type)
            try:
                await self._client.xgroup_create(stream, consumer, id="0", mkstream=True)
                log.info("consumer group created", extra={"stream": stream, "group": consumer})
            except ResponseError as exc:
                if "BUSYGROUP" not in str(exc):
                    raise
            except RedisError as exc:
                raise DependencyError("Event bus is unavailable.") from exc

    async def read(
        self, consumer: str, instance: str, types: Sequence[EventType]
    ) -> list[tuple[str, str, EventEnvelope, int]]:
        results = await self._claim_stale(consumer, instance, types)
        if results:
            return results

        streams = {self._stream(t): ">" for t in types}
        try:
            response = await self._client.xreadgroup(
                consumer,
                instance,
                streams,
                count=self._settings.event_batch_size,
                block=self._settings.event_block_ms,
            )
        except RedisError as exc:
            raise DependencyError("Event bus read failed.") from exc

        return [
            parsed
            for stream, entries in (response or [])
            for entry_id, fields in entries
            if (parsed := self._parse(stream, entry_id, fields, attempt=1)) is not None
        ]

    async def _claim_stale(
        self, consumer: str, instance: str, types: Sequence[EventType]
    ) -> list[tuple[str, str, EventEnvelope, int]]:
        claimed: list[tuple[str, str, EventEnvelope, int]] = []
        for event_type in types:
            stream = self._stream(event_type)
            try:
                _, entries, _ = await self._client.xautoclaim(
                    stream,
                    consumer,
                    instance,
                    min_idle_time=self._settings.event_claim_idle_ms,
                    count=self._settings.event_batch_size,
                )
            except ResponseError:
                continue
            except RedisError as exc:
                raise DependencyError("Event bus claim failed.") from exc

            for entry_id, fields in entries or []:
                attempt = await self._delivery_count(stream, consumer, entry_id)
                parsed = self._parse(stream, entry_id, fields, attempt=attempt)
                if parsed is not None:
                    claimed.append(parsed)
        return claimed

    async def _delivery_count(self, stream: str, consumer: str, entry_id: str) -> int:
        try:
            pending = await self._client.xpending_range(
                stream, consumer, min=entry_id, max=entry_id, count=1
            )
        except RedisError:
            return 1
        if not pending:
            return 1
        return int(pending[0].get("times_delivered", 1))

    def _parse(
        self, stream: str, entry_id: str, fields: dict[str, str], *, attempt: int
    ) -> tuple[str, str, EventEnvelope, int] | None:
        raw = fields.get("envelope")
        if raw is None:
            log.error("event entry missing envelope", extra={"stream": stream})
            return None
        try:
            event = EventEnvelope.model_validate_json(raw)
        except ValueError:
            log.error("event envelope could not be parsed", extra={"stream": stream})
            return None
        return stream, entry_id, event, attempt

    async def ack(self, stream: str, consumer: str, entry_id: str) -> None:
        try:
            await self._client.xack(stream, consumer, entry_id)
        except RedisError as exc:
            log.warning("event ack failed", extra={"stream": stream, "error": str(exc)})

    async def report_depth(self, consumer: str, types: Sequence[EventType]) -> None:
        for event_type in types:
            stream = self._stream(event_type)
            try:
                summary = await self._client.xpending(stream, consumer)
            except RedisError:
                continue
            if summary:
                event_queue_depth.labels(
                    self._service, stream, consumer
                ).set(int(summary.get("pending", 0)))

    async def check(self) -> bool:
        try:
            return bool(await self._client.ping())
        except RedisError:
            return False

    async def close(self) -> None:
        await self._client.aclose()
