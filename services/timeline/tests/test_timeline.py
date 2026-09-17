from __future__ import annotations

from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models import FeedEntry
from tests.conftest import auth_header


async def test_home_feed_requires_auth(client: AsyncClient) -> None:
    response = await client.get("/api/v1/timeline/home")
    assert response.status_code == 401


async def test_home_feed_returns_empty_for_new_user(
    client: AsyncClient, context
) -> None:
    headers = auth_header(context.codec, "user-01")
    response = await client.get("/api/v1/timeline/home", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["entries"] == []
    assert body["has_more"] is False


async def test_user_timeline_requires_auth(client: AsyncClient) -> None:
    response = await client.get("/api/v1/timeline/user/user-01")
    assert response.status_code == 401


async def test_user_timeline_returns_empty(client: AsyncClient, context) -> None:
    headers = auth_header(context.codec, "user-01")
    response = await client.get("/api/v1/timeline/user/user-01", headers=headers)
    assert response.status_code == 200
    assert response.json()["entries"] == []


async def test_home_feed_with_limit(client: AsyncClient, context) -> None:
    headers = auth_header(context.codec, "user-01")
    response = await client.get("/api/v1/timeline/home?limit=5", headers=headers)
    assert response.status_code == 200
    assert response.json()["has_more"] is False


async def test_home_feed_returns_precomputed_entries(
    client: AsyncClient, context
) -> None:
    """Feed entries stored in the DB should appear in the home feed."""
    async with context.database.session() as session:
        session.add(
            FeedEntry(
                user_id="user-01",
                post_id="post-aaa",
                author_id="user-02",
                text="Hello from precomputed feed",
                likes_count=5,
                reposts_count=2,
                replies_count=1,
                created_at=datetime(2025, 1, 1, tzinfo=UTC),
            )
        )
        session.add(
            FeedEntry(
                user_id="user-01",
                post_id="post-bbb",
                author_id="user-03",
                text="Second post in feed",
                created_at=datetime(2025, 1, 2, tzinfo=UTC),
            )
        )
        await session.commit()

    headers = auth_header(context.codec, "user-01")
    response = await client.get("/api/v1/timeline/home", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert len(body["entries"]) == 2
    assert body["entries"][0]["post_id"] == "post-bbb"
    assert body["entries"][0]["text"] == "Second post in feed"
    assert body["entries"][1]["post_id"] == "post-aaa"
    assert body["entries"][1]["likes_count"] == 5


async def test_home_feed_does_not_show_other_users_entries(
    client: AsyncClient, context
) -> None:
    """Entries for other users should not appear in this user's feed."""
    async with context.database.session() as session:
        session.add(
            FeedEntry(
                user_id="user-99",
                post_id="post-xxx",
                author_id="user-02",
                text="Not for user-01",
                created_at=datetime(2025, 1, 1, tzinfo=UTC),
            )
        )
        await session.commit()

    headers = auth_header(context.codec, "user-01")
    response = await client.get("/api/v1/timeline/home", headers=headers)
    assert response.status_code == 200
    assert response.json()["entries"] == []
