from __future__ import annotations

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Notification


class NotificationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, notification: Notification) -> Notification:
        self._session.add(notification)
        await self._session.flush()
        return notification

    async def list_for_user(
        self, user_id: str, limit: int = 20, before: str | None = None
    ) -> list[Notification]:
        stmt = (
            select(Notification)
            .where(Notification.recipient_id == user_id)
            .order_by(Notification.created_at.desc())
            .limit(limit)
        )
        if before:
            from datetime import datetime as _dt
            cursor = _dt.fromisoformat(before) if isinstance(before, str) else before
            stmt = stmt.where(Notification.created_at < cursor)
        return list(await self._session.scalars(stmt))

    async def mark_read(self, user_id: str, notification_id: str) -> bool:
        n = await self._session.get(Notification, notification_id)
        if n is None or n.recipient_id != user_id:
            return False
        n.is_read = True
        return True

    async def mark_all_read(self, user_id: str) -> int:
        stmt = (
            update(Notification)
            .where(Notification.recipient_id == user_id, Notification.is_read.is_(False))
            .values(is_read=True)
        )
        result = await self._session.execute(stmt)
        return result.rowcount

    async def count_unread(self, user_id: str) -> int:
        stmt = select(func.count()).where(
            Notification.recipient_id == user_id, Notification.is_read.is_(False)
        )
        return (await self._session.scalar(stmt)) or 0
