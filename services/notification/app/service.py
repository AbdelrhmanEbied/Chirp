"""Notification domain logic."""

from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from chirp_common.errors import NotFoundError, ForbiddenError
from chirp_common.ids import new_ulid
from app.models import Notification
from app.repository import NotificationRepository
from app.schemas import NotificationResponse, UnreadCountResponse
from app.settings import NotificationSettings

log = logging.getLogger(__name__)


class NotificationService:
    def __init__(
        self,
        *,
        db: AsyncSession,
        notifications: NotificationRepository,
        settings: NotificationSettings,
    ) -> None:
        self._db = db
        self._notifications = notifications
        self._settings = settings

    async def create_notification(
        self,
        recipient_id: str,
        actor_id: str,
        notification_type: str,
        subject_id: str,
    ) -> None:
        if recipient_id == actor_id:
            return
        n = Notification(
            id=new_ulid(),
            recipient_id=recipient_id,
            actor_id=actor_id,
            notification_type=notification_type,
            subject_id=subject_id,
        )
        await self._notifications.add(n)
        log.info(
            "notification created",
            extra={"recipient_id": recipient_id, "type": notification_type},
        )

    async def list_notifications(
        self, user_id: str, limit: int = 20, cursor: str | None = None
    ) -> list[NotificationResponse]:
        items = await self._notifications.list_for_user(user_id, limit=limit, before=cursor)
        return [_to_response(n) for n in items]

    async def mark_read(self, user_id: str, notification_id: str) -> None:
        updated = await self._notifications.mark_read(user_id, notification_id)
        if not updated:
            raise NotFoundError("Notification not found.")

    async def mark_all_read(self, user_id: str) -> None:
        await self._notifications.mark_all_read(user_id)

    async def get_unread_count(self, user_id: str) -> UnreadCountResponse:
        count = await self._notifications.count_unread(user_id)
        return UnreadCountResponse(count=count)


def _to_response(n: Notification) -> NotificationResponse:
    return NotificationResponse(
        id=n.id,
        recipient_id=n.recipient_id,
        actor_id=n.actor_id,
        notification_type=n.notification_type,
        subject_id=n.subject_id,
        is_read=n.is_read,
        created_at=n.created_at,
    )
