from __future__ import annotations

from datetime import timedelta

from httpx import AsyncClient

from chirp_common.timeutil import utcnow
from app.models import UserProfile
from tests.conftest import ADA_ID


async def test_username_can_be_changed(client: AsyncClient, ada, token) -> None:
    response = await client.put(
        "/api/v1/users/me/username", headers=token(ADA_ID), json={"username": "countess"}
    )
    assert response.status_code == 200
    assert response.json()["username"] == "countess"
    assert (await client.get("/api/v1/users/countess")).status_code == 200


async def test_old_username_cannot_be_claimed_by_someone_else(
    client: AsyncClient, ada, token
) -> None:
    """A freed handle is parked so it cannot be used to impersonate."""
    await client.put(
        "/api/v1/users/me/username", headers=token(ADA_ID), json={"username": "countess"}
    )
    response = await client.post(
        "/internal/v1/users",
        json={
            "user_id": "01J0000000000000000000BOB0",
            "username": "ada",
            "display_name": "Impostor",
        },
    )
    assert response.status_code == 409


async def test_cooldown_blocks_a_second_change(
    client: AsyncClient, ada, token, context
) -> None:
    first = await client.put(
        "/api/v1/users/me/username", headers=token(ADA_ID), json={"username": "countess"}
    )
    assert first.status_code == 200

    second = await client.put(
        "/api/v1/users/me/username", headers=token(ADA_ID), json={"username": "lovelace"}
    )
    assert second.status_code == 403
    assert second.json()["error"]["code"] == "username_cooldown"


async def test_cooldown_expires(client: AsyncClient, ada, token, context) -> None:
    await client.put(
        "/api/v1/users/me/username", headers=token(ADA_ID), json={"username": "countess"}
    )
    async with context.database.session() as session:
        profile = await session.get(UserProfile, ADA_ID)
        profile.username_changed_at = utcnow() - timedelta(days=31)

    response = await client.put(
        "/api/v1/users/me/username", headers=token(ADA_ID), json={"username": "lovelace"}
    )
    assert response.status_code == 200


async def test_changing_to_the_same_username_is_a_no_op(
    client: AsyncClient, ada, token
) -> None:
    response = await client.put(
        "/api/v1/users/me/username", headers=token(ADA_ID), json={"username": "ada"}
    )
    assert response.status_code == 200
    assert response.json()["username"] == "ada"
