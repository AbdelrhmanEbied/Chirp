from __future__ import annotations

from httpx import AsyncClient

from tests.conftest import REGISTRATION


def auth_header(tokens: dict) -> dict[str, str]:
    return {"authorization": f"Bearer {tokens['access_token']}"}


async def test_login_succeeds_with_correct_password(
    client: AsyncClient, registered
) -> None:
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": REGISTRATION["email"], "password": REGISTRATION["password"]},
    )
    assert response.status_code == 200
    assert response.json()["user_id"] == registered["user_id"]


async def test_login_fails_with_wrong_password(client: AsyncClient, registered) -> None:
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": REGISTRATION["email"], "password": "definitely-not-it-42"},
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_credentials"


async def test_login_for_unknown_email_gives_the_same_error(client: AsyncClient) -> None:
    """Unknown account and wrong password must be indistinguishable."""
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "nobody@example.com", "password": "definitely-not-it-42"},
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_credentials"


async def test_me_requires_a_token(client: AsyncClient) -> None:
    assert (await client.get("/api/v1/auth/me")).status_code == 401
    bad = await client.get("/api/v1/auth/me", headers={"authorization": "Bearer nope"})
    assert bad.status_code == 401
    assert bad.json()["error"]["code"] == "token_invalid"


async def test_me_returns_the_account(client: AsyncClient, registered) -> None:
    response = await client.get("/api/v1/auth/me", headers=auth_header(registered))
    assert response.status_code == 200
    assert response.json()["email"] == REGISTRATION["email"]
    assert response.json()["is_admin"] is False


async def test_session_cap_revokes_the_oldest_sessions(
    client: AsyncClient, registered
) -> None:
    """max_active_sessions_per_user is 3 in the test settings."""
    for _ in range(4):
        response = await client.post(
            "/api/v1/auth/login",
            json={"email": REGISTRATION["email"], "password": REGISTRATION["password"]},
        )
        assert response.status_code == 200

    listing = await client.get("/api/v1/auth/sessions", headers=auth_header(registered))
    assert listing.status_code == 200
    assert len(listing.json()) <= 3


async def test_change_password_revokes_other_sessions(
    client: AsyncClient, registered
) -> None:
    second = await client.post(
        "/api/v1/auth/login",
        json={"email": REGISTRATION["email"], "password": REGISTRATION["password"]},
    )
    assert second.status_code == 200

    changed = await client.post(
        "/api/v1/auth/password",
        headers=auth_header(registered),
        json={
            "current_password": REGISTRATION["password"],
            "new_password": "a-brand-new-secret-2026",
        },
    )
    assert changed.status_code == 200
    assert changed.json()["revoked_sessions"] >= 2

    # The old refresh token no longer works.
    refreshed = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": second.json()["refresh_token"]}
    )
    assert refreshed.status_code == 401


async def test_sessions_list_shows_current_session(
    client: AsyncClient, registered
) -> None:
    response = await client.get("/api/v1/auth/sessions", headers=auth_header(registered))
    assert response.status_code == 200
    sessions = response.json()
    assert len(sessions) >= 1
    assert any(s["current"] for s in sessions)


async def test_logout_all_requires_auth(client: AsyncClient) -> None:
    response = await client.post("/api/v1/auth/logout-all")
    assert response.status_code == 401
