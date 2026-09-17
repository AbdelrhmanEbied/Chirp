from __future__ import annotations

from httpx import AsyncClient

from chirp_common.events.envelope import EventType
from tests.conftest import ADA_ID


async def test_create_profile_is_idempotent(client: AsyncClient) -> None:
    """The auth service retries this call after a timeout, so a repeat must
    return the same profile rather than a conflict."""
    payload = {"user_id": ADA_ID, "username": "ada", "display_name": "Ada Lovelace"}
    first = await client.post("/internal/v1/users", json=payload)
    second = await client.post("/internal/v1/users", json=payload)

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] == second.json()["id"] == ADA_ID


async def test_username_conflict_for_a_different_user(client: AsyncClient, ada) -> None:
    response = await client.post(
        "/internal/v1/users",
        json={
            "user_id": "01J0000000000000000000BOB0",
            "username": "ADA",
            "display_name": "Impostor",
        },
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "username_taken"


async def test_reserved_usernames_are_refused(client: AsyncClient) -> None:
    response = await client.post(
        "/internal/v1/users",
        json={
            "user_id": "01J0000000000000000000ADM0",
            "username": "admin",
            "display_name": "Nope",
        },
    )
    assert response.status_code == 422


async def test_public_profile_lookup_is_case_insensitive(
    client: AsyncClient, ada
) -> None:
    response = await client.get("/api/v1/users/AdA")
    assert response.status_code == 200
    assert response.json()["username"] == "ada"
    assert response.json()["followers_count"] == 0


async def test_unknown_profile_is_404(client: AsyncClient) -> None:
    response = await client.get("/api/v1/users/nobody")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


async def test_update_profile_requires_auth(client: AsyncClient, ada) -> None:
    assert (await client.patch("/api/v1/users/me", json={"bio": "hi"})).status_code == 401


async def test_update_profile_publishes_an_event(
    client: AsyncClient, ada, token, bus
) -> None:
    response = await client.patch(
        "/api/v1/users/me",
        headers=token(ADA_ID),
        json={"bio": "Analytical engines.", "website": "https://example.com"},
    )
    assert response.status_code == 200
    assert response.json()["bio"] == "Analytical engines."

    events = bus.published_of(EventType.USER_PROFILE_UPDATED)
    assert len(events) == 1
    assert set(events[0].payload["changed_fields"]) == {"bio", "website"}


async def test_website_must_be_http(client: AsyncClient, ada, token) -> None:
    response = await client.patch(
        "/api/v1/users/me", headers=token(ADA_ID), json={"website": "javascript:alert(1)"}
    )
    assert response.status_code == 422


async def test_batch_summaries_hydrate_authors(client: AsyncClient, ada) -> None:
    response = await client.post(
        "/internal/v1/users/summaries", json={"user_ids": [ADA_ID, "01JMISSING0000000000000000"]}
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["username"] == "ada"


async def test_search_matches_prefixes(client: AsyncClient, ada) -> None:
    assert len((await client.get("/api/v1/users/search?q=ad")).json()) == 1
    assert len((await client.get("/api/v1/users/search?q=zz")).json()) == 0
