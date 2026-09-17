from __future__ import annotations

from httpx import AsyncClient

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
