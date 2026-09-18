from __future__ import annotations

from sqlalchemy import case, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import UserProfile, UsernameHistory


class ProfileRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, user_id: str) -> UserProfile | None:
        return await self._session.get(UserProfile, user_id)

    async def get_by_username(self, username: str) -> UserProfile | None:
        return await self._session.scalar(
            select(UserProfile).where(
                UserProfile.username == username.lower(),
                UserProfile.deleted_at.is_(None),
            )
        )

    async def get_many(self, user_ids: list[str]) -> list[UserProfile]:
        if not user_ids:
            return []
        rows = await self._session.scalars(
            select(UserProfile).where(
                UserProfile.id.in_(user_ids), UserProfile.deleted_at.is_(None)
            )
        )
        return list(rows)

    async def username_taken(self, username: str) -> bool:
        current = await self._session.scalar(
            select(UserProfile.id).where(UserProfile.username == username.lower())
        )
        if current is not None:
            return True
        historical = await self._session.scalar(
            select(UsernameHistory.id).where(UsernameHistory.username == username.lower())
        )
        return historical is not None

    async def add(self, profile: UserProfile) -> UserProfile:
        self._session.add(profile)
        await self._session.flush()
        return profile

    async def record_username_release(self, user_id: str, username: str) -> None:
        self._session.add(UsernameHistory(user_id=user_id, username=username))

    async def search(self, query: str, limit: int) -> list[UserProfile]:
        pattern = f"{query.lower()}%"
        rows = await self._session.scalars(
            select(UserProfile)
            .where(
                UserProfile.deleted_at.is_(None),
                (UserProfile.username.like(pattern))
                | (func.lower(UserProfile.display_name).like(pattern)),
            )
            .order_by(UserProfile.followers_count.desc(), UserProfile.username)
            .limit(limit)
        )
        return list(rows)

    async def adjust_counter(self, user_id: str, field: str, delta: int) -> None:
        column = getattr(UserProfile, field)
        updated = column + delta
        await self._session.execute(
            update(UserProfile)
            .where(UserProfile.id == user_id)
            .values({field: case((updated < 0, 0), else_=updated)})
        )
