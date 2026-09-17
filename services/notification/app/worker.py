"""Notification service event consumer.

Runs as a separate process. Consumes events that should generate
user notifications.
"""

from __future__ import annotations

import asyncio
import logging

from chirp_common.events.envelope import EventEnvelope, EventType
from chirp_common.events.worker import EventWorker, build_event_bus
from chirp_common.idempotency import claim_event
from chirp_common.logging import configure_logging
from app.dependencies import ServiceContext
from app.repository import NotificationRepository
from app.service import NotificationService
from app.settings import get_settings

log = logging.getLogger(__name__)

CONSUMER_GROUP = "notification-service"


class NotificationProjector:
    def __init__(self, context: ServiceContext) -> None:
        self._context = context

    async def on_post_liked(self, event: EventEnvelope) -> None:
        async with self._context.database.session() as session:
            if not await claim_event(
                session, event_id=event.id, consumer=CONSUMER_GROUP,
                event_type=event.type.value,
            ):
                return
            recipient_id = str(event.payload.get("author_id", ""))
            actor_id = str(event.actor_id or "")
            if recipient_id and actor_id:
                svc = NotificationService(
                    db=session,
                    notifications=NotificationRepository(session),
                    settings=self._context.settings,
                )
                await svc.create_notification(
                    recipient_id=recipient_id,
                    actor_id=actor_id,
                    notification_type="post_liked",
                    subject_id=event.subject_id,
                )
            await session.commit()

    async def on_reply_created(self, event: EventEnvelope) -> None:
        async with self._context.database.session() as session:
            if not await claim_event(
                session, event_id=event.id, consumer=CONSUMER_GROUP,
                event_type=event.type.value,
            ):
                return
            recipient_id = str(event.payload.get("author_id", ""))
            actor_id = str(event.actor_id or "")
            if recipient_id and actor_id:
                svc = NotificationService(
                    db=session,
                    notifications=NotificationRepository(session),
                    settings=self._context.settings,
                )
                await svc.create_notification(
                    recipient_id=recipient_id,
                    actor_id=actor_id,
                    notification_type="reply_created",
                    subject_id=event.subject_id,
                )
            await session.commit()

    async def on_quote_created(self, event: EventEnvelope) -> None:
        async with self._context.database.session() as session:
            if not await claim_event(
                session, event_id=event.id, consumer=CONSUMER_GROUP,
                event_type=event.type.value,
            ):
                return
            recipient_id = str(event.payload.get("author_id", ""))
            actor_id = str(event.actor_id or "")
            if recipient_id and actor_id:
                svc = NotificationService(
                    db=session,
                    notifications=NotificationRepository(session),
                    settings=self._context.settings,
                )
                await svc.create_notification(
                    recipient_id=recipient_id,
                    actor_id=actor_id,
                    notification_type="quote_created",
                    subject_id=event.subject_id,
                )
            await session.commit()

    async def on_user_mentioned(self, event: EventEnvelope) -> None:
        async with self._context.database.session() as session:
            if not await claim_event(
                session, event_id=event.id, consumer=CONSUMER_GROUP,
                event_type=event.type.value,
            ):
                return
            mentioned_id = str(event.payload.get("mentioned_user_id", ""))
            actor_id = str(event.actor_id or "")
            if mentioned_id and actor_id:
                svc = NotificationService(
                    db=session,
                    notifications=NotificationRepository(session),
                    settings=self._context.settings,
                )
                await svc.create_notification(
                    recipient_id=mentioned_id,
                    actor_id=actor_id,
                    notification_type="user_mentioned",
                    subject_id=event.subject_id,
                )
            await session.commit()

    async def on_user_followed(self, event: EventEnvelope) -> None:
        async with self._context.database.session() as session:
            if not await claim_event(
                session, event_id=event.id, consumer=CONSUMER_GROUP,
                event_type=event.type.value,
            ):
                return
            followee_id = event.subject_id
            actor_id = str(event.actor_id or "")
            if followee_id and actor_id:
                svc = NotificationService(
                    db=session,
                    notifications=NotificationRepository(session),
                    settings=self._context.settings,
                )
                await svc.create_notification(
                    recipient_id=followee_id,
                    actor_id=actor_id,
                    notification_type="user_followed",
                    subject_id=actor_id,
                )
            await session.commit()

    async def on_message_sent(self, event: EventEnvelope) -> None:
        async with self._context.database.session() as session:
            if not await claim_event(
                session, event_id=event.id, consumer=CONSUMER_GROUP,
                event_type=event.type.value,
            ):
                return
            recipient_id = str(event.payload.get("recipient_id", ""))
            actor_id = str(event.actor_id or "")
            if recipient_id and actor_id:
                svc = NotificationService(
                    db=session,
                    notifications=NotificationRepository(session),
                    settings=self._context.settings,
                )
                await svc.create_notification(
                    recipient_id=recipient_id,
                    actor_id=actor_id,
                    notification_type="message_sent",
                    subject_id=event.subject_id,
                )
            await session.commit()


async def main() -> None:
    settings = get_settings()
    configure_logging(f"{settings.service_name}-worker", settings.log_level, json=settings.log_json)

    context = ServiceContext.create(settings)
    projector = NotificationProjector(context)
    bus = build_event_bus(settings, service_name=settings.service_name)

    worker = EventWorker(
        bus=bus,
        settings=settings,
        consumer_group=CONSUMER_GROUP,
        service_name=settings.service_name,
    )
    worker.on(EventType.POST_LIKED, projector.on_post_liked)
    worker.on(EventType.REPLY_CREATED, projector.on_reply_created)
    worker.on(EventType.QUOTE_CREATED, projector.on_quote_created)
    worker.on(EventType.USER_MENTIONED, projector.on_user_mentioned)
    worker.on(EventType.USER_FOLLOWED, projector.on_user_followed)
    worker.on(EventType.MESSAGE_SENT, projector.on_message_sent)
    worker.install_signal_handlers()

    try:
        await worker.run()
    finally:
        await context.close()


if __name__ == "__main__":
    asyncio.run(main())
