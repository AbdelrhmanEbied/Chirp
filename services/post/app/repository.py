from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Bookmark, Like, Post, Repost


class PostRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, post: Post) -> Post:
        self._session.add(post)
        await self._session.flush()
        return post

    async def get(self, post_id: str) -> Post | None:
        return await self._session.get(Post, post_id)

    async def delete(self, post: Post) -> None:
        post.deleted_at = datetime.now(UTC)

    async def list_by_author(self, author_id: str, limit: int = 20, before: str | None = None) -> list[Post]:
        stmt = (
            select(Post)
            .where(Post.author_id == author_id, Post.deleted_at.is_(None))
            .order_by(Post.created_at.desc())
            .limit(limit)
        )
        if before:
            stmt = stmt.where(Post.created_at < func.timezone("UTC", func.now()))
        return list(await self._session.scalars(stmt))

    async def list_replies(self, post_id: str, limit: int = 20) -> list[Post]:
        return list(await self._session.scalars(
            select(Post)
            .where(Post.reply_to_id == post_id, Post.deleted_at.is_(None))
            .order_by(Post.created_at.asc())
            .limit(limit)
        ))

    async def adjust_counter(self, post_id: str, field: str, delta: int) -> None:
        column = getattr(Post, field)
        await self._session.execute(
            update(Post).where(Post.id == post_id).values({field: column + delta})
        )


class LikeRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, like: Like) -> bool:
        self._session.add(like)
        try:
            await self._session.flush()
            return True
        except Exception:
            await self._session.rollback()
            return False

    async def remove(self, user_id: str, post_id: str) -> bool:
        like = await self._session.get(Like, (user_id, post_id))
        if like is None:
            return False
        await self._session.delete(like)
        return True

    async def has_liked(self, user_id: str, post_id: str) -> bool:
        return await self._session.get(Like, (user_id, post_id)) is not None


class RepostRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, repost: Repost) -> bool:
        self._session.add(repost)
        try:
            await self._session.flush()
            return True
        except Exception:
            await self._session.rollback()
            return False

    async def remove(self, user_id: str, post_id: str) -> bool:
        repost = await self._session.get(Repost, (user_id, post_id))
        if repost is None:
            return False
        await self._session.delete(repost)
        return True

    async def has_reposted(self, user_id: str, post_id: str) -> bool:
        return await self._session.get(Repost, (user_id, post_id)) is not None


class BookmarkRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, bookmark: Bookmark) -> bool:
        self._session.add(bookmark)
        try:
            await self._session.flush()
            return True
        except Exception:
            await self._session.rollback()
            return False

    async def remove(self, user_id: str, post_id: str) -> bool:
        bm = await self._session.get(Bookmark, (user_id, post_id))
        if bm is None:
            return False
        await self._session.delete(bm)
        return True

    async def list_user_bookmarks(self, user_id: str, limit: int = 20) -> list[Bookmark]:
        return list(await self._session.scalars(
            select(Bookmark)
            .where(Bookmark.user_id == user_id)
            .order_by(Bookmark.created_at.desc())
            .limit(limit)
        ))
