from __future__ import annotations

from httpx import AsyncClient

from chirp_common.events.envelope import EventType
from tests.conftest import auth_header


async def test_follow_user(client: AsyncClient, context, bus) -> None:
    headers = auth_header(context.codec, "user-01")
    response = await client.post("/api/v1/graph/follow/user-02", headers=headers)
    assert response.status_code == 201
    published = bus.published_of(EventType.USER_FOLLOWED)
    assert len(published) == 1
    assert published[0].subject_id == "user-02"
    assert published[0].actor_id == "user-01"


async def test_unfollow_user(client: AsyncClient, context, bus) -> None:
    headers = auth_header(context.codec, "user-01")
    await client.post("/api/v1/graph/follow/user-02", headers=headers)
    response = await client.delete("/api/v1/graph/follow/user-02", headers=headers)
    assert response.status_code == 204
    published = bus.published_of(EventType.USER_UNFOLLOWED)
    assert len(published) == 1


async def test_self_follow_is_rejected(client: AsyncClient, context) -> None:
    headers = auth_header(context.codec, "user-01")
    response = await client.post("/api/v1/graph/follow/user-01", headers=headers)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "conflict"


async def test_double_follow_is_rejected(client: AsyncClient, context) -> None:
    headers = auth_header(context.codec, "user-01")
    await client.post("/api/v1/graph/follow/user-02", headers=headers)
    response = await client.post("/api/v1/graph/follow/user-02", headers=headers)
    assert response.status_code == 409


async def test_unfollow_without_following_is_404(client: AsyncClient, context) -> None:
    headers = auth_header(context.codec, "user-01")
    response = await client.delete("/api/v1/graph/follow/user-02", headers=headers)
    assert response.status_code == 404


async def test_list_followers(client: AsyncClient, context) -> None:
    headers1 = auth_header(context.codec, "user-01")
    headers2 = auth_header(context.codec, "user-02")
    await client.post("/api/v1/graph/follow/user-01", headers=headers2)
    response = await client.get("/api/v1/graph/user-01/followers")
    assert response.status_code == 200
    assert len(response.json()) == 1


async def test_list_following(client: AsyncClient, context) -> None:
    headers = auth_header(context.codec, "user-01")
    await client.post("/api/v1/graph/follow/user-02", headers=headers)
    response = await client.get("/api/v1/graph/user-01/following")
    assert response.status_code == 200
    assert len(response.json()) == 1


async def test_block_user(client: AsyncClient, context, bus) -> None:
    headers = auth_header(context.codec, "user-01")
    response = await client.post("/api/v1/graph/block/user-02", headers=headers)
    assert response.status_code == 201
    published = bus.published_of(EventType.USER_BLOCKED)
    assert len(published) == 1


async def test_unblock_user(client: AsyncClient, context, bus) -> None:
    headers = auth_header(context.codec, "user-01")
    await client.post("/api/v1/graph/block/user-02", headers=headers)
    response = await client.delete("/api/v1/graph/block/user-02", headers=headers)
    assert response.status_code == 204
    published = bus.published_of(EventType.USER_UNBLOCKED)
    assert len(published) == 1


async def test_self_block_is_rejected(client: AsyncClient, context) -> None:
    headers = auth_header(context.codec, "user-01")
    response = await client.post("/api/v1/graph/block/user-01", headers=headers)
    assert response.status_code == 409


async def test_mute_user(client: AsyncClient, context) -> None:
    headers = auth_header(context.codec, "user-01")
    response = await client.post("/api/v1/graph/mute/user-02", headers=headers)
    assert response.status_code == 201


async def test_unmute_user(client: AsyncClient, context) -> None:
    headers = auth_header(context.codec, "user-01")
    await client.post("/api/v1/graph/mute/user-02", headers=headers)
    response = await client.delete("/api/v1/graph/mute/user-02", headers=headers)
    assert response.status_code == 204


async def test_self_mute_is_rejected(client: AsyncClient, context) -> None:
    headers = auth_header(context.codec, "user-01")
    response = await client.post("/api/v1/graph/mute/user-01", headers=headers)
    assert response.status_code == 409


async def test_batch_block_check(client: AsyncClient, context) -> None:
    headers = auth_header(context.codec, "user-01")
    await client.post("/api/v1/graph/block/user-02", headers=headers)
    response = await client.post(
        "/internal/v1/graph/check-blocks",
        json={"blocker_id": "user-01", "target_ids": ["user-02", "user-03"]},
        headers=headers,
    )
    assert response.status_code == 200
    result = response.json()
    assert "user-02" in result["blocked_ids"]
    assert "user-03" not in result["blocked_ids"]


async def test_follow_requires_auth(client: AsyncClient) -> None:
    response = await client.post("/api/v1/graph/follow/user-01")
    assert response.status_code == 401


async def test_list_blocks(client: AsyncClient, context) -> None:
    headers = auth_header(context.codec, "user-01")
    await client.post("/api/v1/graph/block/user-02", headers=headers)
    await client.post("/api/v1/graph/block/user-03", headers=headers)
    response = await client.get("/api/v1/graph/blocks", headers=headers)
    assert response.status_code == 200
    assert len(response.json()) == 2
