from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Media


class MediaRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, media: Media) -> Media:
        self._session.add(media)
        await self._session.flush()
        return media

    async def get(self, media_id: str) -> Media | None:
        return await self._session.get(Media, media_id)

    async def delete(self, media: Media) -> None:
        await self._session.delete(media)
        await self._session.flush()

    async def list_for_user(self, owner_id: str, limit: int = 20) -> list[Media]:
        stmt = (
            select(Media)
            .where(Media.owner_id == owner_id)
            .order_by(Media.created_at.desc())
            .limit(limit)
        )
        return list(await self._session.scalars(stmt))
