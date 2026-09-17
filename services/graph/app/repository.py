from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Block, Follow, Mute


class FollowRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, follower_id: str, followee_id: str) -> Follow:
        follow = Follow(follower_id=follower_id, followee_id=followee_id)
        self._session.add(follow)
        await self._session.flush()
        return follow

    async def remove(self, follower_id: str, followee_id: str) -> None:
        follow = await self._session.get(Follow, (follower_id, followee_id))
        if follow is not None:
            await self._session.delete(follow)
            await self._session.flush()

    async def get(self, follower_id: str, followee_id: str) -> Follow | None:
        return await self._session.get(Follow, (follower_id, followee_id))

    async def list_followers(
        self, user_id: str, *, limit: int = 50, offset: int = 0
    ) -> list[Follow]:
        rows = await self._session.scalars(
            select(Follow)
            .where(Follow.followee_id == user_id)
            .order_by(Follow.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(rows)

    async def list_following(
        self, user_id: str, *, limit: int = 50, offset: int = 0
    ) -> list[Follow]:
        rows = await self._session.scalars(
            select(Follow)
            .where(Follow.follower_id == user_id)
            .order_by(Follow.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(rows)

    async def count_followers(self, user_id: str) -> int:
        return await self._session.scalar(
            select(func.count()).where(Follow.followee_id == user_id)
        )

    async def count_following(self, user_id: str) -> int:
        return await self._session.scalar(
            select(func.count()).where(Follow.follower_id == user_id)
        )

    async def is_following(self, follower_id: str, followee_id: str) -> bool:
        return await self.get(follower_id, followee_id) is not None


class BlockRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, blocker_id: str, blocked_id: str) -> Block:
        block = Block(blocker_id=blocker_id, blocked_id=blocked_id)
        self._session.add(block)
        await self._session.flush()
        return block

    async def remove(self, blocker_id: str, blocked_id: str) -> None:
        block = await self._session.get(Block, (blocker_id, blocked_id))
        if block is not None:
            await self._session.delete(block)
            await self._session.flush()

    async def is_blocked(self, blocker_id: str, blocked_id: str) -> bool:
        return await self._session.get(Block, (blocker_id, blocked_id)) is not None

    async def get_blocks_between(
        self, user_id: str, other_ids: list[str]
    ) -> list[str]:
        if not other_ids:
            return []
        rows = await self._session.scalars(
            select(Block.blocked_id).where(
                Block.blocker_id == user_id,
                Block.blocked_id.in_(other_ids),
            )
        )
        return list(rows)


class MuteRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, user_id: str, muted_id: str) -> Mute:
        mute = Mute(user_id=user_id, muted_id=muted_id)
        self._session.add(mute)
        await self._session.flush()
        return mute

    async def remove(self, user_id: str, muted_id: str) -> None:
        mute = await self._session.get(Mute, (user_id, muted_id))
        if mute is not None:
            await self._session.delete(mute)
            await self._session.flush()
