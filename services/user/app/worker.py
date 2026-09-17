"""User service event consumer.

Runs as its own process (`services/user` image, different command). It keeps
the denormalised counters on `user_profiles` in step with the follow and post
events published by other services.

Why counters are maintained here rather than queried live: a profile page is
read far more often than a follow is created, and `SELECT COUNT(*) FROM
follows WHERE followee_id = ?` on a popular account is an index scan over
millions of rows on every view. The cost of that choice is eventual
consistency -- the number can lag by the queue depth -- which is acceptable for
a follower count and is documented in docs/scalability.md.
"""

from __future__ import annotations

import asyncio
import logging

from chirp_common.events.envelope import EventEnvelope, EventType
from chirp_common.events.worker import EventWorker, build_event_bus
from chirp_common.idempotency import claim_event
from chirp_common.logging import configure_logging
from app.dependencies import ServiceContext
from app.repository import ProfileRepository
from app.settings import get_settings

log = logging.getLogger(__name__)

CONSUMER_GROUP = "user-service"


class CounterProjector:
    """Applies counter deltas, exactly once per event."""

    def __init__(self, context: ServiceContext) -> None:
        self._context = context

    async def on_followed(self, event: EventEnvelope) -> None:
        await self._apply(
            event,
            [
                (event.subject_id, "followers_count", 1),
                (str(event.payload.get("follower_id", "")), "following_count", 1),
            ],
        )

    async def on_unfollowed(self, event: EventEnvelope) -> None:
        await self._apply(
            event,
            [
                (event.subject_id, "followers_count", -1),
                (str(event.payload.get("follower_id", "")), "following_count", -1),
            ],
        )

    async def on_post_created(self, event: EventEnvelope) -> None:
        author_id = str(event.payload.get("author_id") or event.actor_id or "")
        await self._apply(event, [(author_id, "posts_count", 1)])

    async def on_post_deleted(self, event: EventEnvelope) -> None:
        author_id = str(event.payload.get("author_id") or event.actor_id or "")
        await self._apply(event, [(author_id, "posts_count", -1)])

    async def _apply(
        self, event: EventEnvelope, deltas: list[tuple[str, str, int]]
    ) -> None:
        async with self._context.database.session() as session:
            # The claim and the deltas share one transaction: either both
            # commit or neither does, so a redelivery cannot double-count.
            first_time = await claim_event(
                session,
                event_id=event.id,
                consumer=CONSUMER_GROUP,
                event_type=event.type.value,
            )
            if not first_time:
                log.info("duplicate event ignored", extra={"event_id": event.id})
                return

            profiles = ProfileRepository(session)
            for user_id, field, delta in deltas:
                if user_id:
                    await profiles.adjust_counter(user_id, field, delta)


async def main() -> None:
    settings = get_settings()
    configure_logging(f"{settings.service_name}-worker", settings.log_level, json=settings.log_json)

    context = ServiceContext.create(settings)
    projector = CounterProjector(context)
    bus = build_event_bus(settings, service_name=settings.service_name)

    worker = EventWorker(
        bus=bus,
        settings=settings,
        consumer_group=CONSUMER_GROUP,
        service_name=settings.service_name,
    )
    worker.on(EventType.USER_FOLLOWED, projector.on_followed)
    worker.on(EventType.USER_UNFOLLOWED, projector.on_unfollowed)
    worker.on(EventType.POST_CREATED, projector.on_post_created)
    worker.on(EventType.POST_DELETED, projector.on_post_deleted)
    worker.install_signal_handlers()

    try:
        await worker.run()
    finally:
        await context.close()


if __name__ == "__main__":
    asyncio.run(main())
