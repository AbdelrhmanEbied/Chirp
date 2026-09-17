"""Event consumer runtime.

A worker is a separate process from the HTTP API even when it belongs to the
same service. A slow fan-out or a search reindex must not consume the web
worker pool that is serving user requests, and the two scale on different
signals: API on request rate, worker on queue depth.

Delivery semantics are at-least-once. Handlers are expected to be idempotent,
either naturally or via `chirp_common.idempotency.claim_event`.
"""

from __future__ import annotations

import asyncio
import logging
import signal
import time
from collections import defaultdict
from collections.abc import Sequence
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select

from chirp_common import context
from chirp_common.config import EventBusSettings
from chirp_common.errors import DependencyError
from chirp_common.events.bus import EventBus, EventHandler
from chirp_common.events.envelope import EventEnvelope, EventType
from chirp_common.events.memory import InMemoryEventBus
from chirp_common.events.redis_streams import RedisStreamsEventBus
from chirp_common.db.session import Database
from chirp_common.ids import new_ulid
from chirp_common.idempotency import ProcessedEvent
from chirp_common.metrics import (
    event_processing_duration_seconds,
    events_consumed_total,
)

log = logging.getLogger(__name__)


def build_event_bus(settings: EventBusSettings, *, service_name: str) -> EventBus:
    """Select the bus implementation. The only place a backend is named."""
    if settings.event_bus_backend == "memory":
        return InMemoryEventBus(service_name)
    return RedisStreamsEventBus(settings, service_name=service_name)


class EventWorker:
    def __init__(
        self,
        *,
        bus: EventBus,
        settings: EventBusSettings,
        consumer_group: str,
        service_name: str,
        instance_id: str | None = None,
        database: Database | None = None,
    ) -> None:
        self._bus = bus
        self._settings = settings
        self._group = consumer_group
        self._service = service_name
        self._instance = instance_id or f"{consumer_group}-{new_ulid()[-8:]}"
        self._handlers: dict[EventType, list[EventHandler]] = defaultdict(list)
        self._stopping = asyncio.Event()
        self._database = database

    def on(self, event_type: EventType, handler: EventHandler) -> None:
        self._handlers[event_type].append(handler)

    @property
    def subscribed_types(self) -> Sequence[EventType]:
        return tuple(self._handlers)

    def install_signal_handlers(self) -> None:
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, self.stop)

    def stop(self) -> None:
        log.info("worker shutdown requested", extra={"consumer": self._group})
        self._stopping.set()

    async def run(self) -> None:
        if not self._handlers:
            raise RuntimeError("EventWorker started with no registered handlers.")

        await self._bus.ensure_groups(self._group, self.subscribed_types)
        log.info(
            "worker started",
            extra={
                "consumer": self._group,
                "instance": self._instance,
                "subscriptions": [t.value for t in self.subscribed_types],
            },
        )

        backoff = self._settings.event_retry_base_delay_seconds
        events_since_cleanup = 0
        last_cleanup = time.monotonic()
        while not self._stopping.is_set():
            try:
                batch = await self._bus.read(
                    self._group, self._instance, self.subscribed_types
                )
                backoff = self._settings.event_retry_base_delay_seconds
            except DependencyError:
                # Broker is down. Back off instead of spinning, and cap the
                # delay so the worker recovers promptly when it returns.
                log.warning("event bus unavailable", extra={"retry_in": backoff})
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, self._settings.event_retry_max_delay_seconds)
                continue

            for stream, entry_id, event, attempt in batch:
                if self._stopping.is_set():
                    break
                await self._dispatch(stream, entry_id, event, attempt)

            events_since_cleanup += len(batch)
            now = time.monotonic()
            if events_since_cleanup >= 1000 or (now - last_cleanup) >= 300:
                await self._cleanup_processed_events()
                events_since_cleanup = 0
                last_cleanup = now

            if not batch:
                await asyncio.sleep(0.05)

        await self._bus.close()
        log.info("worker stopped", extra={"consumer": self._group})

    async def _dispatch(
        self, stream: str, entry_id: str, event: EventEnvelope, attempt: int
    ) -> None:
        handlers = self._handlers.get(event.type, [])
        if not handlers:
            await self._bus.ack(stream, self._group, entry_id)
            return

        with context.bind_context(
            correlation_id=event.correlation_id,
            actor_id=event.actor_id,
        ):
            started = time.perf_counter()
            try:
                for handler in handlers:
                    await handler(event)
            except Exception as exc:  # noqa: BLE001 - one bad event must not kill the loop
                await self._handle_failure(stream, entry_id, event, attempt, exc)
                return
            finally:
                event_processing_duration_seconds.labels(
                    self._service, event.type.value
                ).observe(time.perf_counter() - started)

            await self._bus.ack(stream, self._group, entry_id)
            events_consumed_total.labels(self._service, event.type.value, "ok").inc()
            log.info(
                "event processed",
                extra={
                    "event_id": event.id,
                    "event_type": event.type.value,
                    "attempt": attempt,
                },
            )

    async def _cleanup_processed_events(self) -> None:
        """Delete ProcessedEvent records older than 7 days."""
        if self._database is None:
            return
        cutoff = datetime.now(timezone.utc) - timedelta(days=7)
        try:
            async with self._database.session() as session:
                stmt = delete(ProcessedEvent).where(
                    ProcessedEvent.processed_at < cutoff
                )
                result = await session.execute(stmt)
                await session.commit()
                if result.rowcount:
                    log.info(
                        "cleaned up old processed events",
                        extra={"deleted": result.rowcount, "consumer": self._group},
                    )
        except Exception:  # noqa: BLE001
            log.warning("failed to clean up processed events", exc_info=True)

    async def _handle_failure(
        self,
        stream: str,
        entry_id: str,
        event: EventEnvelope,
        attempt: int,
        exc: Exception,
    ) -> None:
        if attempt >= self._settings.event_max_delivery_attempts:
            # Give up: park it and acknowledge, otherwise this entry blocks its
            # pending list forever and every claim cycle retries it.
            await self._bus.dead_letter(event, reason=f"{type(exc).__name__}: {exc}")
            await self._bus.ack(stream, self._group, entry_id)
            events_consumed_total.labels(
                self._service, event.type.value, "dead_lettered"
            ).inc()
            log.error(
                "event exhausted retries",
                exc_info=exc,
                extra={"event_id": event.id, "attempts": attempt},
            )
            return

        # Leave the entry unacknowledged. It stays in the consumer group's
        # pending list and is reclaimed by `xautoclaim` after the idle window,
        # which spreads retries out rather than hot-looping on a bad event.
        events_consumed_total.labels(self._service, event.type.value, "retry").inc()
        log.warning(
            "event handler failed, will retry",
            exc_info=exc,
            extra={"event_id": event.id, "event_type": event.type.value, "attempt": attempt},
        )
