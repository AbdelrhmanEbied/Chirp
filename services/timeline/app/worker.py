
from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime, timedelta

from chirp_common.events.envelope import EventEnvelope, EventType
from chirp_common.events.worker import EventWorker, build_event_bus
from chirp_common.http.client import ServiceClient
from chirp_common.idempotency import claim_event
from chirp_common.logging import configure_logging
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import ServiceContext
from app.models import FeedEntry
from app.settings import get_settings

log = logging.getLogger(__name__)

CONSUMER_GROUP = "timeline-service"

CELEBRITY_FOLLOWER_THRESHOLD = 10_000

ACTIVE_FOLLOWER_DAYS = 7

MAX_FEED_ENTRIES_PER_USER = 800


class TimelineProjector:
    def __init__(self, context: ServiceContext) -> None:
        self._context = context

    async def on_post_created(self, event: EventEnvelope) -> None:
        async with self._context.database.session() as session:
            if not await claim_event(
                session, event_id=event.id, consumer=CONSUMER_GROUP,
                event_type=event.type.value,
            ):
                return

            author_id = event.actor_id or event.payload.get("author_id", "")
            post_id = event.subject_id
            text = event.payload.get("text", "")
            likes_count = event.payload.get("likes_count", 0)
            reposts_count = event.payload.get("reposts_count", 0)
            replies_count = event.payload.get("replies_count", 0)
            created_at_str = event.payload.get("created_at")

            if created_at_str:
                try:
                    created_at = datetime.fromisoformat(created_at_str)
                except (ValueError, TypeError):
                    created_at = event.occurred_at
            else:
                created_at = event.occurred_at

            follower_ids = await self._fetch_followers(author_id)

            if not follower_ids:
                await session.commit()
                log.info("no followers for fan-out", extra={"author_id": author_id})
                return

            if len(follower_ids) >= CELEBRITY_FOLLOWER_THRESHOLD:
                log.info(
                    "celebrity post, skipping fan-out",
                    extra={"author_id": author_id, "follower_count": len(follower_ids)},
                )
                await session.commit()
                return

            active_followers = await self._filter_active_followers(
                session, follower_ids
            )

            entries = [
                FeedEntry(
                    user_id=fid,
                    post_id=post_id,
                    author_id=author_id,
                    text=text,
                    likes_count=likes_count,
                    reposts_count=reposts_count,
                    replies_count=replies_count,
                    created_at=created_at,
                )
                for fid in active_followers
            ]
            session.add_all(entries)
            await session.commit()

            log.info(
                "fan-out complete",
                extra={
                    "post_id": post_id,
                    "author_id": author_id,
                    "fan_out_count": len(entries),
                    "total_followers": len(follower_ids),
                    "active_followers": len(active_followers),
                },
            )

    async def on_post_deleted(self, event: EventEnvelope) -> None:
        async with self._context.database.session() as session:
            if not await claim_event(
                session, event_id=event.id, consumer=CONSUMER_GROUP,
                event_type=event.type.value,
            ):
                return

            post_id = event.subject_id
            await session.execute(
                delete(FeedEntry).where(FeedEntry.post_id == post_id)
            )
            await session.commit()
            log.info("removed post from all feeds", extra={"post_id": post_id})

    async def on_user_followed(self, event: EventEnvelope) -> None:
        async with self._context.database.session() as session:
            if not await claim_event(
                session, event_id=event.id, consumer=CONSUMER_GROUP,
                event_type=event.type.value,
            ):
                return

            follower_id = event.actor_id or ""
            followee_id = event.subject_id

            posts = await self._fetch_user_posts(followee_id, limit=50)

            if posts:
                entries = [
                    FeedEntry(
                        user_id=follower_id,
                        post_id=p["id"],
                        author_id=p["author_id"],
                        text=p["text"],
                        likes_count=p.get("likes_count", 0),
                        reposts_count=p.get("reposts_count", 0),
                        replies_count=p.get("replies_count", 0),
                        created_at=p["created_at"],
                    )
                    for p in posts
                ]
                session.add_all(entries)
                await session.commit()

            log.info(
                "backfill complete",
                extra={
                    "follower_id": follower_id,
                    "followee_id": followee_id,
                    "backfilled": len(entries) if posts else 0,
                },
            )

    async def on_user_unfollowed(self, event: EventEnvelope) -> None:
        async with self._context.database.session() as session:
            if not await claim_event(
                session, event_id=event.id, consumer=CONSUMER_GROUP,
                event_type=event.type.value,
            ):
                return

            follower_id = event.actor_id or ""
            followee_id = event.subject_id

            await session.execute(
                delete(FeedEntry).where(
                    FeedEntry.user_id == follower_id,
                    FeedEntry.author_id == followee_id,
                )
            )
            await session.commit()
            log.info(
                "removed unfollowed user's posts",
                extra={"follower_id": follower_id, "followee_id": followee_id},
            )

    async def _fetch_followers(self, user_id: str) -> list[str]:
        try:
            followers = await self._context.graph_client.get(
                f"/internal/v1/graph/{user_id}/followers",
                params={"limit": 50000},
            )
            return [f["follower_id"] for f in followers]
        except Exception:  # noqa: BLE001
            log.warning("failed to fetch followers", extra={"user_id": user_id})
            return []

    async def _filter_active_followers(
        self, session: AsyncSession, follower_ids: list[str]
    ) -> list[str]:
        cutoff = datetime.now(UTC) - timedelta(days=ACTIVE_FOLLOWER_DAYS)

        result = await session.execute(
            select(FeedEntry.user_id)
            .where(
                FeedEntry.user_id.in_(follower_ids),
                FeedEntry.inserted_at >= cutoff,
            )
            .distinct()
        )
        active = set(result.scalars().all())

        result2 = await session.execute(
            select(FeedEntry.user_id)
            .where(FeedEntry.user_id.in_(follower_ids))
            .distinct()
        )
        has_entries = set(result2.scalars().all())

        return [fid for fid in follower_ids if fid in active or fid in has_entries]

    async def _fetch_user_posts(
        self, user_id: str, limit: int = 50
    ) -> list[dict]:
        try:
            return await self._context.post_client.get(
                f"/internal/v1/posts/by/{user_id}",
                params={"limit": limit},
            )
        except Exception:  # noqa: BLE001
            log.warning("failed to fetch user posts for backfill", extra={"user_id": user_id})
            return []


async def main() -> None:
    settings = get_settings()
    configure_logging(
        f"{settings.service_name}-worker", settings.log_level, json=settings.log_json
    )

    context = ServiceContext.create(settings)
    projector = TimelineProjector(context)
    bus = build_event_bus(settings, service_name=settings.service_name)

    worker = EventWorker(
        bus=bus,
        settings=settings,
        consumer_group=CONSUMER_GROUP,
        service_name=settings.service_name,
    )
    worker.on(EventType.POST_CREATED, projector.on_post_created)
    worker.on(EventType.POST_DELETED, projector.on_post_deleted)
    worker.on(EventType.USER_FOLLOWED, projector.on_user_followed)
    worker.on(EventType.USER_UNFOLLOWED, projector.on_user_unfollowed)
    worker.install_signal_handlers()

    try:
        await worker.run()
    finally:
        await context.close()


if __name__ == "__main__":
    asyncio.run(main())
