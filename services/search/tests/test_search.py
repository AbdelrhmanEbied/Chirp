from __future__ import annotations

from datetime import datetime, timezone

from httpx import AsyncClient

from chirp_common.events.envelope import EventEnvelope, EventType
from chirp_common.testing.factories import make_event
from app.models import PostSearch, HashtagUsage
from app.repository import PostSearchRepository, HashtagRepository


async def test_search_posts_empty(client: AsyncClient) -> None:
    response = await client.get("/api/v1/search/posts", params={"q": "hello"})
    assert response.status_code == 200
    assert response.json()["results"] == []


async def test_search_posts_requires_query(client: AsyncClient) -> None:
    response = await client.get("/api/v1/search/posts")
    assert response.status_code == 422


async def test_trending_empty(client: AsyncClient) -> None:
    response = await client.get("/api/v1/search/trending")
    assert response.status_code == 200
    assert response.json() == []


async def test_search_users_proxies_to_user_service(
    client: AsyncClient, context
) -> None:
    response = await client.get("/api/v1/search/users?q=test")
    assert response.status_code == 200


async def test_search_posts_after_indexing(client: AsyncClient, context) -> None:
    async with context.database.session() as session:
        from app.models import PostSearch
        from chirp_common.ids import new_ulid
        repo = PostSearchRepository(session)
        post = PostSearch(
            id=new_ulid(),
            post_id="post-01",
            author_id="user-01",
            text="Hello world",
            created_at_index=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        await repo.index(post)
        await session.commit()

    response = await client.get("/api/v1/search/posts", params={"q": "Hello"})
    assert response.status_code == 200
    results = response.json()["results"]
    assert len(results) >= 1


async def test_trending_after_increment(client: AsyncClient, context) -> None:
    async with context.database.session() as session:
        repo = HashtagRepository(session)
        await repo.increment("chirp")
        await repo.increment("chirp")
        await repo.increment("testing")
        await session.commit()

    response = await client.get("/api/v1/search/trending")
    assert response.status_code == 200
    hashtags = response.json()
    assert len(hashtags) == 2
    assert hashtags[0]["hashtag"] == "chirp"
    assert hashtags[0]["usage_count"] == 2
