from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import HashtagUsage, PostSearch


class PostSearchRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def index(self, post: PostSearch) -> PostSearch:
        self._session.add(post)
        await self._session.flush()
        return post

    async def remove(self, post_id: str) -> bool:
        post = await self._session.execute(
            select(PostSearch).where(PostSearch.post_id == post_id)
        )
        row = post.scalar_one_or_none()
        if row is None:
            return False
        await self._session.delete(row)
        return True

    async def search(self, query: str, limit: int = 20) -> list[PostSearch]:
        stmt = (
            select(PostSearch)
            .where(PostSearch.text.ilike(f"%{query}%"))
            .order_by(PostSearch.created_at_index.desc())
            .limit(limit)
        )
        return list(await self._session.scalars(stmt))

    async def get(self, post_id: str) -> PostSearch | None:
        result = await self._session.execute(
            select(PostSearch).where(PostSearch.post_id == post_id)
        )
        return result.scalar_one_or_none()


class HashtagRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def increment(self, hashtag: str, count: int = 1) -> None:
        from sqlalchemy import update
        result = await self._session.execute(
            update(HashtagUsage)
            .where(HashtagUsage.hashtag == hashtag)
            .values(usage_count=HashtagUsage.usage_count + count)
        )
        if result.rowcount == 0:
            self._session.add(HashtagUsage(hashtag=hashtag, usage_count=count))
        await self._session.flush()

    async def get_trending(self, limit: int = 10) -> list[HashtagUsage]:
        stmt = (
            select(HashtagUsage)
            .order_by(HashtagUsage.usage_count.desc())
            .limit(limit)
        )
        return list(await self._session.scalars(stmt))
