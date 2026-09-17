from __future__ import annotations

from httpx import AsyncClient

from chirp_common.events.envelope import EventType
from tests.conftest import auth_header


async def test_create_conversation(client: AsyncClient, context) -> None:
    headers = auth_header(context.codec, "user-01")
    response = await client.post(
        "/api/v1/messages/conversations",
        json={"participant_ids": ["user-02"]},
        headers=headers,
    )
    assert response.status_code == 201
    body = response.json()
    assert "id" in body


async def test_list_conversations_empty(client: AsyncClient, context) -> None:
    headers = auth_header(context.codec, "user-01")
    response = await client.get("/api/v1/messages/conversations", headers=headers)
    assert response.status_code == 200
    assert response.json() == []


async def test_send_message(client: AsyncClient, context, bus) -> None:
    headers1 = auth_header(context.codec, "user-01")
    create = await client.post(
        "/api/v1/messages/conversations",
        json={"participant_ids": ["user-02"]},
        headers=headers1,
    )
    conv_id = create.json()["id"]

    response = await client.post(
        f"/api/v1/messages/conversations/{conv_id}/messages",
        json={"text": "Hello!"},
        headers=headers1,
    )
    assert response.status_code == 201
    assert response.json()["text"] == "Hello!"

    published = bus.published_of(EventType.MESSAGE_SENT)
    assert len(published) == 1


async def test_list_messages(client: AsyncClient, context) -> None:
    headers1 = auth_header(context.codec, "user-01")
    create = await client.post(
        "/api/v1/messages/conversations",
        json={"participant_ids": ["user-02"]},
        headers=headers1,
    )
    conv_id = create.json()["id"]

    await client.post(
        f"/api/v1/messages/conversations/{conv_id}/messages",
        json={"text": "Hello!"},
        headers=headers1,
    )
    await client.post(
        f"/api/v1/messages/conversations/{conv_id}/messages",
        json={"text": "World!"},
        headers=headers1,
    )

    response = await client.get(
        f"/api/v1/messages/conversations/{conv_id}/messages",
        headers=headers1,
    )
    assert response.status_code == 200
    messages = response.json()
    assert len(messages) == 2
    assert messages[0]["text"] == "Hello!"
    assert messages[1]["text"] == "World!"


async def test_mark_read(client: AsyncClient, context) -> None:
    headers1 = auth_header(context.codec, "user-01")
    create = await client.post(
        "/api/v1/messages/conversations",
        json={"participant_ids": ["user-02"]},
        headers=headers1,
    )
    conv_id = create.json()["id"]

    response = await client.post(
        f"/api/v1/messages/conversations/{conv_id}/read",
        headers=headers1,
    )
    assert response.status_code == 204


async def test_send_message_requires_auth(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/messages/conversations/fake-id/messages",
        json={"text": "no auth"},
    )
    assert response.status_code == 401


async def test_empty_participant_list_is_rejected(client: AsyncClient, context) -> None:
    headers = auth_header(context.codec, "user-01")
    response = await client.post(
        "/api/v1/messages/conversations",
        json={"participant_ids": []},
        headers=headers,
    )
    assert response.status_code in (400, 422)
