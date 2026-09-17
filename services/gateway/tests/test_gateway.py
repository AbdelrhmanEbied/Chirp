from __future__ import annotations

from httpx import AsyncClient

from chirp_common.testing.factories import TEST_JWT_SECRET
from chirp_common.auth.jwt import JWTCodec
from tests.conftest import auth_header


codec = JWTCodec(
    secret=TEST_JWT_SECRET,
    issuer="chirp.auth",
    audience="chirp.api",
    access_ttl_seconds=900,
)


async def test_liveness(client: AsyncClient) -> None:
    response = await client.get("/health/live")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


async def test_readiness(client: AsyncClient) -> None:
    response = await client.get("/health/ready")
    assert response.status_code in (200, 503)


async def test_metrics(client: AsyncClient) -> None:
    response = await client.get("/metrics")
    assert response.status_code == 200
    assert "chirp_http_requests_total" in response.text


async def test_register_proxied_to_auth(client: AsyncClient, context) -> None:
    fake = context._fake_clients["auth"]  # type: ignore[attr-defined]
    fake.set_response({
        "access_token": "test-token",
        "refresh_token": "test-refresh",
        "token_type": "Bearer",
        "expires_in": 900,
        "user_id": "user-01",
    })

    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "test@example.com",
            "username": "testuser",
            "display_name": "Test User",
            "password": "secure-password-123",
        },
    )
    assert response.status_code == 201
    assert len(fake.calls) == 1
    assert fake.calls[0]["path"] == "/api/v1/auth/register"


async def test_login_proxied_to_auth(client: AsyncClient, context) -> None:
    fake = context._fake_clients["auth"]  # type: ignore[attr-defined]
    fake.set_response({
        "access_token": "test-token",
        "refresh_token": "test-refresh",
        "token_type": "Bearer",
        "expires_in": 900,
        "user_id": "user-01",
    })

    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "test@example.com", "password": "secure-password-123"},
    )
    assert response.status_code == 200
    assert len(fake.calls) == 1


async def test_get_me_proxied_to_user(client: AsyncClient, context) -> None:
    fake = context._fake_clients["user"]  # type: ignore[attr-defined]
    fake.set_response({
        "id": "user-01",
        "username": "testuser",
        "display_name": "Test User",
    })

    headers = auth_header(codec, "user-01")
    response = await client.get("/api/v1/users/me", headers=headers)
    assert response.status_code == 200


async def test_unauthenticated_proxied_route_returns_401(
    client: AsyncClient,
) -> None:
    response = await client.get("/api/v1/users/me")
    assert response.status_code == 401


async def test_create_post_proxied(client: AsyncClient, context) -> None:
    fake = context._fake_clients["post"]  # type: ignore[attr-defined]
    fake.set_response({
        "id": "post-01",
        "author_id": "user-01",
        "text": "Hello!",
        "likes_count": 0,
        "reposts_count": 0,
        "replies_count": 0,
        "quotes_count": 0,
        "created_at": "2026-01-01T00:00:00Z",
    })

    headers = auth_header(codec, "user-01")
    response = await client.post(
        "/api/v1/posts",
        json={"text": "Hello!"},
        headers=headers,
    )
    assert response.status_code == 201


async def test_follow_proxied_to_graph(client: AsyncClient, context) -> None:
    fake = context._fake_clients["graph"]  # type: ignore[attr-defined]
    fake.set_response(None)

    headers = auth_header(codec, "user-01")
    response = await client.post("/api/v1/graph/follow/user-02", headers=headers)
    assert response.status_code in (200, 201, 204)


async def test_search_proxied(client: AsyncClient, context) -> None:
    fake = context._fake_clients["search"]  # type: ignore[attr-defined]
    fake.set_response({"results": [], "hashtags": []})

    headers = auth_header(codec, "user-01")
    response = await client.get("/api/v1/search/posts?q=test", headers=headers)
    assert response.status_code == 200


async def test_request_id_generated(client: AsyncClient) -> None:
    response = await client.get("/health/live")
    assert "x-request-id" in response.headers
    assert len(response.headers["x-request-id"]) > 0
