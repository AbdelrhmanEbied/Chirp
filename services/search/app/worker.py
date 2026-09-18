
from __future__ import annotations

import asyncio
import logging

from chirp_common.events.envelope import EventEnvelope, EventType
from chirp_common.events.worker import EventWorker, build_event_bus
from chirp_common.idempotency import claim_event
from chirp_common.logging import configure_logging

from app.dependencies import ServiceContext
from app.repository import HashtagRepository, PostSearchRepository
from app.settings import get_settings

log = logging.getLogger(__name__)

CONSUMER_GROUP = "search-service"


class SearchProjector:
    def __init__(self, context: ServiceContext) -> None:
        self._context = context

    async def on_post_created(self, event: EventEnvelope) -> None:
        async with self._context.database.session() as session:
            if not await claim_event(
                session, event_id=event.id, consumer=CONSUMER_GROUP,
                event_type=event.type.value,
            ):
                return

            from app.service import SearchService
            from app.settings import get_settings

            service = SearchService(
                db=session,
                posts=PostSearchRepository(session),
                hashtags=HashtagRepository(session),
                settings=get_settings(),
            )
            await service.index_post(
                post_id=event.subject_id,
                author_id=event.payload.get("author_id", ""),
                text=event.payload.get("text", ""),
                created_at=event.occurred_at.isoformat(),
            )

            for hashtag in event.payload.get("hashtags", []):
                await service.increment_hashtag(hashtag)
            await session.commit()

            log.info("indexed post", extra={"post_id": event.subject_id})

    async def on_post_deleted(self, event: EventEnvelope) -> None:
        async with self._context.database.session() as session:
            if not await claim_event(
                session, event_id=event.id, consumer=CONSUMER_GROUP,
                event_type=event.type.value,
            ):
                return

            from app.service import SearchService
            from app.settings import get_settings

            service = SearchService(
                db=session,
                posts=PostSearchRepository(session),
                hashtags=HashtagRepository(session),
                settings=get_settings(),
            )
            await service.remove_post(event.subject_id)
            await session.commit()

            log.info("removed post from index", extra={"post_id": event.subject_id})

    async def on_hashtag_used(self, event: EventEnvelope) -> None:
        async with self._context.database.session() as session:
            if not await claim_event(
                session, event_id=event.id, consumer=CONSUMER_GROUP,
                event_type=event.type.value,
            ):
                return

            from app.repository import HashtagRepository

            repo = HashtagRepository(session)
            hashtag = event.payload.get("hashtag", "")
            if hashtag:
                await repo.increment(hashtag)
                await session.commit()

            log.info("incremented hashtag", extra={"hashtag": hashtag})


async def main() -> None:
    settings = get_settings()
    configure_logging(
        f"{settings.service_name}-worker",
        settings.log_level,
        json=settings.log_json,
    )

    context = ServiceContext.create(settings)
    projector = SearchProjector(context)
    bus = build_event_bus(settings, service_name=settings.service_name)

    worker = EventWorker(
        bus=bus,
        settings=settings,
        consumer_group=CONSUMER_GROUP,
        service_name=settings.service_name,
    )
    worker.on(EventType.POST_CREATED, projector.on_post_created)
    worker.on(EventType.POST_DELETED, projector.on_post_deleted)
    worker.on(EventType.HASHTAG_USED, projector.on_hashtag_used)
    worker.install_signal_handlers()

    try:
        await worker.run()
    finally:
        await context.close()


if __name__ == "__main__":
    asyncio.run(main())
