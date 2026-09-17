"""Post service event consumer.

Runs as a separate process. Consumes events that affect post counts
or need post-service side effects.
"""

from __future__ import annotations

import asyncio
import logging

from chirp_common.events.envelope import EventEnvelope, EventType
from chirp_common.events.worker import EventWorker, build_event_bus
from chirp_common.idempotency import claim_event
from chirp_common.logging import configure_logging
from app.dependencies import ServiceContext
from app.repository import PostRepository
from app.settings import get_settings

log = logging.getLogger(__name__)

CONSUMER_GROUP = "post-service"


class PostProjector:
    def __init__(self, context: ServiceContext) -> None:
        self._context = context

    async def on_user_deleted(self, event: EventEnvelope) -> None:
        async with self._context.database.session() as session:
            if not await claim_event(
                session, event_id=event.id, consumer=CONSUMER_GROUP,
                event_type=event.type.value,
            ):
                return
            from datetime import UTC, datetime
            from sqlalchemy import update
            from app.models import Post
            user_id = event.subject_id
            await session.execute(
                update(Post)
                .where(Post.author_id == user_id, Post.deleted_at.is_(None))
                .values(deleted_at=datetime.now(UTC))
            )
            await session.commit()
            log.info("soft-deleted posts for user", extra={"user_id": user_id})

    async def on_user_followed(self, event: EventEnvelope) -> None:
        async with self._context.database.session() as session:
            if not await claim_event(
                session, event_id=event.id, consumer=CONSUMER_GROUP,
                event_type=event.type.value,
            ):
                return
            log.info("follow event noted", extra={"event_id": event.id})


async def main() -> None:
    settings = get_settings()
    configure_logging(f"{settings.service_name}-worker", settings.log_level, json=settings.log_json)

    context = ServiceContext.create(settings)
    projector = PostProjector(context)
    bus = build_event_bus(settings, service_name=settings.service_name)

    worker = EventWorker(
        bus=bus,
        settings=settings,
        consumer_group=CONSUMER_GROUP,
        service_name=settings.service_name,
    )
    worker.on(EventType.USER_DELETED, projector.on_user_deleted)
    worker.on(EventType.USER_FOLLOWED, projector.on_user_followed)
    worker.install_signal_handlers()

    try:
        await worker.run()
    finally:
        await context.close()


if __name__ == "__main__":
    asyncio.run(main())
