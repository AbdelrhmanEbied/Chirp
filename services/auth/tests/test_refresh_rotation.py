from __future__ import annotations

from httpx import AsyncClient


async def test_refresh_returns_a_new_pair(client: AsyncClient, registered) -> None:
    response = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": registered["refresh_token"]}
    )
    assert response.status_code == 200
    rotated = response.json()
    assert rotated["refresh_token"] != registered["refresh_token"]
    assert rotated["user_id"] == registered["user_id"]


async def test_reusing_a_rotated_token_revokes_every_session(
    client: AsyncClient, registered
) -> None:
    first = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": registered["refresh_token"]}
    )
    assert first.status_code == 200
    new_token = first.json()["refresh_token"]

    replay = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": registered["refresh_token"]}
    )
    assert replay.status_code == 401
    assert replay.json()["error"]["code"] == "refresh_reuse"

    after = await client.post("/api/v1/auth/refresh", json={"refresh_token": new_token})
    assert after.status_code == 401


async def test_unknown_refresh_token_is_rejected(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": "x" * 40}
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_refresh"


async def test_logout_revokes_the_refresh_token(client: AsyncClient, registered) -> None:
    logout = await client.post(
        "/api/v1/auth/logout", json={"refresh_token": registered["refresh_token"]}
    )
    assert logout.status_code == 204

    response = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": registered["refresh_token"]}
    )
    assert response.status_code == 401


async def test_logout_is_idempotent(client: AsyncClient, registered) -> None:
    for _ in range(2):
        response = await client.post(
            "/api/v1/auth/logout", json={"refresh_token": registered["refresh_token"]}
        )
        assert response.status_code == 204
