"""Timeline repository: fan-out-on-write with pre-computed feeds.

Home feed reads from the local feed_entries table (O(1) query).
User timeline still fetches from the post service on-read.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from chirp_common.http.client import ServiceClient
from chirp_common.pagination import encode_cursor
from app.models import FeedEntry
from app.schemas import FeedResponse, TimelineEntry

log = logging.getLogger(__name__)


class TimelineRepository:
    def __init__(
        self,
        *,
        session: AsyncSession,
        post_client: ServiceClient,
        user_client: ServiceClient,
        max_feed_size: int,
    ) -> None:
        self._session = session
        self._post = post_client
        self._user = user_client
        self._max_feed_size = max_feed_size

    async def get_home_feed(
        self, user_id: str, limit: int, cursor: str | None
    ) -> FeedResponse:
        """Read pre-computed home feed from feed_entries table."""
        effective_limit = min(limit, self._max_feed_size)

        stmt = (
            select(FeedEntry)
            .where(FeedEntry.user_id == user_id)
            .order_by(desc(FeedEntry.created_at))
            .limit(effective_limit + 1)
        )

        if cursor:
            from chirp_common.pagination import decode_cursor
            cursor_id = decode_cursor(cursor)
            stmt = stmt.where(FeedEntry.post_id < cursor_id)

        rows = list(await self._session.scalars(stmt))

        has_more = len(rows) > effective_limit
        rows = rows[:effective_limit]

        entries = [
            TimelineEntry(
                post_id=row.post_id,
                author_id=row.author_id,
                text=row.text,
                likes_count=row.likes_count,
                reposts_count=row.reposts_count,
                replies_count=row.replies_count,
                created_at=row.created_at,
            )
            for row in rows
        ]

        # Hydrate author info if we have entries
        if entries:
            author_ids = list({e.author_id for e in entries})
            author_map = await self._hydrate_authors(author_ids)
            for entry in entries:
                author = author_map.get(entry.author_id, {})
                entry.author_username = author.get("username")
                entry.author_display_name = author.get("display_name")
                entry.author_avatar_media_id = author.get("avatar_media_id")

        next_cursor = None
        if has_more and entries:
            next_cursor = encode_cursor(entries[-1].post_id)

        return FeedResponse(entries=entries, next_cursor=next_cursor, has_more=has_more)

    async def get_user_timeline(
        self, user_id: str, limit: int, cursor: str | None
    ) -> FeedResponse:
        """Posts by a specific user (still fan-out on read since it's per-user)."""
        effective_limit = min(limit, self._max_feed_size)

        params: dict[str, Any] = {"limit": effective_limit + 1}
        if cursor:
            params["before"] = cursor

        posts = await self._post.get(
            f"/internal/v1/posts/by/{user_id}",
            params=params,
        )

        has_more = len(posts) > effective_limit
        posts = posts[:effective_limit]

        author_map = await self._hydrate_authors([user_id])
        author = author_map.get(user_id, {})

        entries = [
            TimelineEntry(
                post_id=post["id"],
                author_id=post["author_id"],
                text=post["text"],
                likes_count=post.get("likes_count", 0),
                reposts_count=post.get("reposts_count", 0),
                replies_count=post.get("replies_count", 0),
                created_at=post["created_at"],
                author_username=author.get("username"),
                author_display_name=author.get("display_name"),
                author_avatar_media_id=author.get("avatar_media_id"),
            )
            for post in posts
        ]

        next_cursor = None
        if has_more and entries:
            next_cursor = encode_cursor(entries[-1].post_id)

        return FeedResponse(entries=entries, next_cursor=next_cursor, has_more=has_more)

    async def _hydrate_authors(self, author_ids: list[str]) -> dict[str, dict[str, Any]]:
        if not author_ids:
            return {}
        try:
            summaries = await self._user.request(
                "POST",
                "/internal/v1/users/summaries",
                json={"user_ids": author_ids},
            )
            return {s["id"]: s for s in summaries}
        except Exception:  # noqa: BLE001
            log.warning("failed to hydrate authors", extra={"author_ids": author_ids})
            return {}
