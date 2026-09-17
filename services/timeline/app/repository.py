"""Timeline repository: fan-out on read assembling data from graph and post services."""

from __future__ import annotations

import logging
from typing import Any

from chirp_common.http.client import ServiceClient
from chirp_common.pagination import encode_cursor
from app.schemas import FeedResponse, TimelineEntry

log = logging.getLogger(__name__)


class TimelineRepository:
    def __init__(
        self,
        *,
        post_client: ServiceClient,
        graph_client: ServiceClient,
        user_client: ServiceClient,
        max_feed_size: int,
    ) -> None:
        self._post = post_client
        self._graph = graph_client
        self._user = user_client
        self._max_feed_size = max_feed_size

    async def get_home_feed(
        self, user_id: str, limit: int, cursor: str | None
    ) -> FeedResponse:
        """Fan-out on read: fetch followees' recent posts and hydrate authors."""
        effective_limit = min(limit, self._max_feed_size)

        # 1. Get followees from the graph service
        followees_data = await self._graph.get(
            f"/internal/v1/graph/{user_id}/following",
            params={"limit": 500},
        )
        followee_ids = [f["followee_id"] for f in followees_data]

        if not followee_ids:
            return FeedResponse(entries=[], has_more=False)

        # 2. Get recent posts from each followee (batch by fetching from post service)
        all_posts: list[dict[str, Any]] = []
        for fid in followee_ids:
            params: dict[str, Any] = {"limit": effective_limit}
            if cursor:
                params["before"] = cursor
            posts = await self._post.get(
                f"/internal/v1/posts/by/{fid}",
                params=params,
            )
            all_posts.extend(posts)

        # 3. Sort by created_at descending and take the top N
        all_posts.sort(key=lambda p: p["created_at"], reverse=True)
        page = all_posts[: effective_limit + 1]
        has_more = len(page) > effective_limit
        page = page[:effective_limit]

        # 4. Hydrate author info from user service summaries
        author_ids = list({p["author_id"] for p in page})
        author_map = await self._hydrate_authors(author_ids)

        entries = []
        for post in page:
            author = author_map.get(post["author_id"], {})
            entries.append(
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
            )

        next_cursor = None
        if has_more and entries:
            next_cursor = encode_cursor(entries[-1].post_id)

        return FeedResponse(entries=entries, next_cursor=next_cursor, has_more=has_more)

    async def get_user_timeline(
        self, user_id: str, limit: int, cursor: str | None
    ) -> FeedResponse:
        """Posts by a specific user."""
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

        # Hydrate author info
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
        """Batch author hydration via the user service's internal summaries endpoint."""
        if not author_ids:
            return {}

        summaries = await self._user.request(
            "POST",
            "/internal/v1/users/summaries",
            json={"user_ids": author_ids},
        )
        return {s["id"]: s for s in summaries}
