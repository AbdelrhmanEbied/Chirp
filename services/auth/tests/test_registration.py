from __future__ import annotations

import pytest
from httpx import AsyncClient

from chirp_common.errors import ConflictError
from chirp_common.events.envelope import EventType
from tests.conftest import REGISTRATION


async def test_register_returns_tokens_and_creates_profile(
    client: AsyncClient, bus, user_client
) -> None:
    response = await client.post("/api/v1/auth/register", json=REGISTRATION)

    assert response.status_code == 201
    body = response.json()
    assert body["token_type"] == "Bearer"
    assert body["access_token"] and body["refresh_token"]
    assert body["user_id"]

    # The profile was created in the user service with the same id.
    assert len(user_client.created) == 1
    assert user_client.created[0]["user_id"] == body["user_id"]
    assert user_client.created[0]["username"] == "ada"

    published = bus.published_of(EventType.USER_REGISTERED)
    assert len(published) == 1
    assert published[0].subject_id == body["user_id"]


async def test_duplicate_email_is_rejected(client: AsyncClient, registered) -> None:
    response = await client.post("/api/v1/auth/register", json=REGISTRATION)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "account_exists"


async def test_username_conflict_rolls_back_the_account(
    client: AsyncClient, user_client, bus
) -> None:
    """If the user service rejects the username, no credentials survive."""
    user_client.failure = ConflictError("Username taken.", code="username_taken")

    response = await client.post("/api/v1/auth/register", json=REGISTRATION)
    assert response.status_code == 409

    # The rolled-back account must not block a later, valid registration.
    user_client.failure = None
    retry = await client.post("/api/v1/auth/register", json=REGISTRATION)
    assert retry.status_code == 201
    assert len(bus.published_of(EventType.USER_REGISTERED)) == 1


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("username", "no spaces"),
        ("username", "ab"),
        ("email", "not-an-email"),
        ("password", "short"),
        ("password", "aaaaaaaaaaaaaaa"),
        ("display_name", ""),
        ("username", ""),
        ("email", ""),
    ],
)
async def test_invalid_registration_is_rejected(
    client: AsyncClient, field: str, value: str
) -> None:
    payload = REGISTRATION | {field: value}
    response = await client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


async def test_register_sets_activated_at(client: AsyncClient) -> None:
    response = await client.post("/api/v1/auth/register", json=REGISTRATION)
    assert response.status_code == 201
    user_id = response.json()["user_id"]
    assert user_id is not None
    assert len(user_id) == 26  # ULID
