from __future__ import annotations

from httpx import AsyncClient

from chirp_common.events.envelope import EventEnvelope, EventType
from chirp_common.testing.factories import make_event
from tests.conftest import auth_header
from app.service import NotificationService
from app.repository import NotificationRepository


async def test_list_notifications_requires_auth(client: AsyncClient) -> None:
    response = await client.get("/api/v1/notifications")
    assert response.status_code == 401


async def test_list_notifications_empty(client: AsyncClient, context) -> None:
    headers = auth_header(context.codec, "user-01")
    response = await client.get("/api/v1/notifications", headers=headers)
    assert response.status_code == 200
    assert response.json() == []


async def test_unread_count(client: AsyncClient, context) -> None:
    headers = auth_header(context.codec, "user-01")
    response = await client.get("/api/v1/notifications/unread-count", headers=headers)
    assert response.status_code == 200
    assert response.json()["count"] == 0


async def test_unread_count_after_notification(client: AsyncClient, context) -> None:
    async with context.database.session() as session:
        svc = NotificationService(
            db=session,
            notifications=NotificationRepository(session),
            settings=context.settings,
        )
        await svc.create_notification(
            recipient_id="user-01",
            actor_id="user-02",
            notification_type="post_liked",
            subject_id="post-01",
        )
        await session.commit()

    headers = auth_header(context.codec, "user-01")
    response = await client.get("/api/v1/notifications/unread-count", headers=headers)
    assert response.json()["count"] == 1


async def test_list_notifications_with_data(client: AsyncClient, context) -> None:
    async with context.database.session() as session:
        svc = NotificationService(
            db=session,
            notifications=NotificationRepository(session),
            settings=context.settings,
        )
        await svc.create_notification(
            recipient_id="user-01",
            actor_id="user-02",
            notification_type="user_followed",
            subject_id="user-02",
        )
        await session.commit()

    headers = auth_header(context.codec, "user-01")
    response = await client.get("/api/v1/notifications", headers=headers)
    assert response.status_code == 200
    assert len(response.json()) == 1


async def test_mark_all_read(client: AsyncClient, context) -> None:
    async with context.database.session() as session:
        svc = NotificationService(
            db=session,
            notifications=NotificationRepository(session),
            settings=context.settings,
        )
        await svc.create_notification(
            recipient_id="user-01",
            actor_id="user-02",
            notification_type="post_liked",
            subject_id="post-01",
        )
        await session.commit()

    headers = auth_header(context.codec, "user-01")
    response = await client.post("/api/v1/notifications/read-all", headers=headers)
    assert response.status_code == 204

    count = await client.get("/api/v1/notifications/unread-count", headers=headers)
    assert count.json()["count"] == 0


async def test_self_notification_not_created(client: AsyncClient, context) -> None:
    async with context.database.session() as session:
        svc = NotificationService(
            db=session,
            notifications=NotificationRepository(session),
            settings=context.settings,
        )
        result = await svc.create_notification(
            recipient_id="user-01",
            actor_id="user-01",
            notification_type="post_liked",
            subject_id="post-01",
        )
        await session.commit()
        assert result is None  # Self-notification skipped


async def test_mark_read_requires_auth(client: AsyncClient) -> None:
    response = await client.post("/api/v1/notifications/anything/read")
    assert response.status_code == 401


async def test_notification_type_variations(client: AsyncClient, context) -> None:
    types = ["post_liked", "reply_created", "quote_created", "user_followed", "user_mentioned", "message_sent"]
    async with context.database.session() as session:
        svc = NotificationService(
            db=session,
            notifications=NotificationRepository(session),
            settings=context.settings,
        )
        for ntype in types:
            await svc.create_notification(
                recipient_id="user-01",
                actor_id="user-02",
                notification_type=ntype,
                subject_id="subject-01",
            )
        await session.commit()

    headers = auth_header(context.codec, "user-01")
    response = await client.get("/api/v1/notifications?limit=10", headers=headers)
    assert len(response.json()) == 6
