from __future__ import annotations

import logging

import httpx
from chirp_common.ids import new_ulid
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import PostSearch
from app.repository import HashtagRepository, PostSearchRepository
from app.schemas import SearchResponse, SearchResult, TrendingHashtag
from app.settings import SearchSettings

log = logging.getLogger(__name__)


class SearchService:
    def __init__(
        self,
        *,
        db: AsyncSession,
        posts: PostSearchRepository,
        hashtags: HashtagRepository,
        settings: SearchSettings,
    ) -> None:
        self._db = db
        self._posts = posts
        self._hashtags = hashtags
        self._settings = settings

    async def index_post(
        self, post_id: str, author_id: str, text: str, created_at: str
    ) -> None:
        existing = await self._posts.get(post_id)
        if existing:
            return
        post = PostSearch(
            id=new_ulid(),
            post_id=post_id,
            author_id=author_id,
            text=text,
            created_at_index=created_at,
        )
        await self._posts.index(post)

    async def remove_post(self, post_id: str) -> None:
        await self._posts.remove(post_id)

    async def search_posts(self, query: str, limit: int = 20) -> SearchResponse:
        posts = await self._posts.search(query, limit=limit)
        results = [
            SearchResult(
                id=p.id,
                post_id=p.post_id,
                author_id=p.author_id,
                text=p.text,
                created_at=p.created_at_index,
            )
            for p in posts
        ]
        return SearchResponse(results=results, total=len(results), limit=limit)

    async def search_users(self, query: str, limit: int = 20) -> list[dict]:
        url = f"{self._settings.user_service_url}/api/v1/users/search"
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(url, params={"q": query, "limit": limit})
                resp.raise_for_status()
                return resp.json()
        except httpx.HTTPError:
            log.warning("Failed to call user service for search")
            return []

    async def get_trending(self, limit: int = 10) -> list[TrendingHashtag]:
        hashtags = await self._hashtags.get_trending(limit=limit)
        return [
            TrendingHashtag(hashtag=h.hashtag, usage_count=h.usage_count)
            for h in hashtags
        ]

    async def increment_hashtag(self, hashtag: str) -> None:
        await self._hashtags.increment(hashtag)
