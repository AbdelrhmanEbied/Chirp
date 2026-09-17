from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import HashtagUsage, PostSearch
from chirp_common.pagination import decode_cursor, encode_cursor


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

    async def search(
        self,
        query: str,
        limit: int = 20,
        cursor: str | None = None,
        sort: str = "relevance",
    ) -> tuple[list[PostSearch], str | None]:
        """Search posts using FTS on PostgreSQL or ILIKE on SQLite."""
        dialect = self._session.bind.dialect.name

        if dialect == "postgresql":
            return await self._search_pg(query, limit, cursor, sort)
        return await self._search_sqlite(query, limit, cursor, sort)

    async def _search_pg(
        self,
        query: str,
        limit: int,
        cursor: str | None,
        sort: str,
    ) -> tuple[list[PostSearch], str | None]:
        """PostgreSQL: FTS + trigram hybrid with ts_rank."""
        from sqlalchemy.dialects.postgresql import TSVECTOR, insert as pg_insert

        tsquery = func.plainto_tsquery("english", query)
        text_search = func.cast(PostSearch.text, TSVECTOR)

        if sort == "recent":
            stmt = select(PostSearch).order_by(PostSearch.created_at_index.desc())
        elif sort == "similarity":
            similarity = func.similarity(PostSearch.text, query)
            stmt = (
                select(PostSearch)
                .where(similarity > 0.1)
                .order_by(similarity.desc(), PostSearch.created_at_index.desc())
            )
        else:
            # Relevance: FTS rank + trigram similarity hybrid
            ts_rank = func.ts_rank(text_search, tsquery)
            similarity = func.similarity(PostSearch.text, query)
            stmt = (
                select(PostSearch)
                .where(
                    text_search.op("@@")(tsquery)
                    | (similarity > 0.2)
                )
                .order_by(
                    (ts_rank + similarity * 0.5).desc(),
                    PostSearch.created_at_index.desc(),
                )
            )

        return await self._paginate(stmt, limit, cursor)

    async def _search_sqlite(
        self,
        query: str,
        limit: int,
        cursor: str | None,
        sort: str,
    ) -> tuple[list[PostSearch], str | None]:
        """SQLite fallback: ILIKE substring search (tests only)."""
        if sort == "similarity":
            stmt = select(PostSearch).order_by(PostSearch.created_at_index.desc())
        else:
            stmt = (
                select(PostSearch)
                .where(PostSearch.text.ilike(f"%{query}%"))
                .order_by(PostSearch.created_at_index.desc())
            )

        return await self._paginate(stmt, limit, cursor)

    async def _paginate(
        self, stmt, limit: int, cursor: str | None
    ) -> tuple[list[PostSearch], str | None]:
        """Apply cursor pagination to any query."""
        if cursor:
            cursor_parts = decode_cursor(cursor)
            if ":" in cursor_parts:
                ts_str, post_id = cursor_parts.split(":", 1)
                try:
                    cursor_dt = datetime.fromisoformat(ts_str)
                    stmt = stmt.where(
                        (PostSearch.created_at_index < cursor_dt)
                        | (
                            (PostSearch.created_at_index == cursor_dt)
                            & (PostSearch.post_id < post_id)
                        )
                    )
                except ValueError:
                    pass

        stmt = stmt.limit(limit + 1)
        rows = list(await self._session.scalars(stmt))

        has_more = len(rows) > limit
        rows = rows[:limit]

        next_cursor = None
        if has_more and rows:
            last = rows[-1]
            next_cursor = encode_cursor(
                f"{last.created_at_index.isoformat()}:{last.post_id}"
            )

        return rows, next_cursor

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
