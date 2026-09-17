from __future__ import annotations

from httpx import AsyncClient

from chirp_common.events.envelope import EventType
from chirp_common.auth.jwt import JWTCodec
from chirp_common.testing.factories import TEST_JWT_SECRET


def _auth_header(codec: JWTCodec, user_id: str) -> dict[str, str]:
    token, _ = codec.issue_access_token(user_id=user_id, session_id="test-session")
    return {"authorization": f"Bearer {token}"}


async def test_create_post(client: AsyncClient, context, bus) -> None:
    headers = _auth_header(context.codec, "user-01")
    response = await client.post(
        "/api/v1/posts", json={"text": "Hello, world!"}, headers=headers,
    )
    assert response.status_code == 201
    body = response.json()
    assert body["text"] == "Hello, world!"
    assert body["author_id"] == "user-01"
    assert body["likes_count"] == 0

    published = bus.published_of(EventType.POST_CREATED)
    assert len(published) == 1
    assert published[0].subject_id == body["id"]


async def test_create_post_with_mentions_and_hashtags(
    client: AsyncClient, context, bus
) -> None:
    headers = _auth_header(context.codec, "user-01")
    response = await client.post(
        "/api/v1/posts",
        json={"text": "Hello @alice! #chirp #testing"},
        headers=headers,
    )
    assert response.status_code == 201
    published = bus.published_of(EventType.POST_CREATED)
    assert len(published) == 1
    assert "alice" in published[0].payload["mentions"]
    assert "chirp" in published[0].payload["hashtags"]
    assert "testing" in published[0].payload["hashtags"]


async def test_get_post(client: AsyncClient, context) -> None:
    headers = _auth_header(context.codec, "user-01")
    create = await client.post(
        "/api/v1/posts", json={"text": "test post"}, headers=headers
    )
    post_id = create.json()["id"]

    response = await client.get(f"/api/v1/posts/{post_id}")
    assert response.status_code == 200
    assert response.json()["text"] == "test post"
    assert response.json()["id"] == post_id


async def test_get_nonexistent_post_returns_404(client: AsyncClient, context) -> None:
    response = await client.get("/api/v1/posts/00000000000000000000000000")
    assert response.status_code == 404


async def test_delete_post(client: AsyncClient, context, bus) -> None:
    headers = _auth_header(context.codec, "user-01")
    create = await client.post(
        "/api/v1/posts", json={"text": "delete me"}, headers=headers
    )
    post_id = create.json()["id"]

    response = await client.delete(f"/api/v1/posts/{post_id}", headers=headers)
    assert response.status_code == 204

    published = bus.published_of(EventType.POST_DELETED)
    assert len(published) == 1

    # Post should be gone
    get_resp = await client.get(f"/api/v1/posts/{post_id}")
    assert get_resp.status_code == 404


async def test_delete别人的_post_is_forbidden(client: AsyncClient, context) -> None:
    headers1 = _auth_header(context.codec, "user-01")
    headers2 = _auth_header(context.codec, "user-02")
    create = await client.post(
        "/api/v1/posts", json={"text": "not yours"}, headers=headers1
    )
    post_id = create.json()["id"]

    response = await client.delete(f"/api/v1/posts/{post_id}", headers=headers2)
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"


async def test_like_post(client: AsyncClient, context, bus) -> None:
    headers1 = _auth_header(context.codec, "user-01")
    headers2 = _auth_header(context.codec, "user-02")
    create = await client.post(
        "/api/v1/posts", json={"text": "likeable"}, headers=headers1
    )
    post_id = create.json()["id"]

    response = await client.post(f"/api/v1/posts/{post_id}/like", headers=headers2)
    assert response.status_code == 204

    published = bus.published_of(EventType.POST_LIKED)
    assert len(published) == 1


async def test_double_like_is_rejected(client: AsyncClient, context) -> None:
    headers1 = _auth_header(context.codec, "user-01")
    headers2 = _auth_header(context.codec, "user-02")
    create = await client.post(
        "/api/v1/posts", json={"text": "likeable"}, headers=headers1
    )
    post_id = create.json()["id"]

    await client.post(f"/api/v1/posts/{post_id}/like", headers=headers2)
    response = await client.post(f"/api/v1/posts/{post_id}/like", headers=headers2)
    assert response.status_code == 409


async def test_unlike_post(client: AsyncClient, context) -> None:
    headers1 = _auth_header(context.codec, "user-01")
    headers2 = _auth_header(context.codec, "user-02")
    create = await client.post(
        "/api/v1/posts", json={"text": "likeable"}, headers=headers1
    )
    post_id = create.json()["id"]

    await client.post(f"/api/v1/posts/{post_id}/like", headers=headers2)
    response = await client.delete(f"/api/v1/posts/{post_id}/like", headers=headers2)
    assert response.status_code == 204


async def test_unlike_without_liking_is_404(client: AsyncClient, context) -> None:
    headers1 = _auth_header(context.codec, "user-01")
    headers2 = _auth_header(context.codec, "user-02")
    create = await client.post(
        "/api/v1/posts", json={"text": "not liked"}, headers=headers1
    )
    post_id = create.json()["id"]

    response = await client.delete(f"/api/v1/posts/{post_id}/like", headers=headers2)
    assert response.status_code == 404


async def test_repost(client: AsyncClient, context, bus) -> None:
    headers1 = _auth_header(context.codec, "user-01")
    headers2 = _auth_header(context.codec, "user-02")
    create = await client.post(
        "/api/v1/posts", json={"text": "repostable"}, headers=headers1
    )
    post_id = create.json()["id"]

    response = await client.post(f"/api/v1/posts/{post_id}/repost", headers=headers2)
    assert response.status_code == 204

    published = bus.published_of(EventType.POST_REPOSTED)
    assert len(published) == 1


async def test_double_repost_is_rejected(client: AsyncClient, context) -> None:
    headers1 = _auth_header(context.codec, "user-01")
    headers2 = _auth_header(context.codec, "user-02")
    create = await client.post(
        "/api/v1/posts", json={"text": "repostable"}, headers=headers1
    )
    post_id = create.json()["id"]

    await client.post(f"/api/v1/posts/{post_id}/repost", headers=headers2)
    response = await client.post(f"/api/v1/posts/{post_id}/repost", headers=headers2)
    assert response.status_code == 409


async def test_unrepost(client: AsyncClient, context) -> None:
    headers1 = _auth_header(context.codec, "user-01")
    headers2 = _auth_header(context.codec, "user-02")
    create = await client.post(
        "/api/v1/posts", json={"text": "repostable"}, headers=headers1
    )
    post_id = create.json()["id"]

    await client.post(f"/api/v1/posts/{post_id}/repost", headers=headers2)
    response = await client.delete(f"/api/v1/posts/{post_id}/repost", headers=headers2)
    assert response.status_code == 204


async def test_bookmark(client: AsyncClient, context) -> None:
    headers1 = _auth_header(context.codec, "user-01")
    headers2 = _auth_header(context.codec, "user-02")
    create = await client.post(
        "/api/v1/posts", json={"text": "bookmarkable"}, headers=headers1
    )
    post_id = create.json()["id"]

    response = await client.post(f"/api/v1/posts/{post_id}/bookmark", headers=headers2)
    assert response.status_code == 204


async def test_unbookmark(client: AsyncClient, context) -> None:
    headers1 = _auth_header(context.codec, "user-01")
    headers2 = _auth_header(context.codec, "user-02")
    create = await client.post(
        "/api/v1/posts", json={"text": "bookmarkable"}, headers=headers1
    )
    post_id = create.json()["id"]

    await client.post(f"/api/v1/posts/{post_id}/bookmark", headers=headers2)
    response = await client.delete(f"/api/v1/posts/{post_id}/bookmark", headers=headers2)
    assert response.status_code == 204


async def test_unbookmark_without_booking_is_404(client: AsyncClient, context) -> None:
    headers1 = _auth_header(context.codec, "user-01")
    headers2 = _auth_header(context.codec, "user-02")
    create = await client.post(
        "/api/v1/posts", json={"text": "not bookmarked"}, headers=headers1
    )
    post_id = create.json()["id"]

    response = await client.delete(f"/api/v1/posts/{post_id}/bookmark", headers=headers2)
    assert response.status_code == 404


async def test_list_user_posts(client: AsyncClient, context) -> None:
    headers = _auth_header(context.codec, "user-01")
    for i in range(5):
        await client.post(
            "/api/v1/posts", json={"text": f"post {i}"}, headers=headers
        )

    response = await client.get("/api/v1/posts/by/user-01")
    assert response.status_code == 200
    assert len(response.json()) == 5


async def test_list_user_posts_with_limit(client: AsyncClient, context) -> None:
    headers = _auth_header(context.codec, "user-01")
    for i in range(5):
        await client.post(
            "/api/v1/posts", json={"text": f"post {i}"}, headers=headers
        )

    response = await client.get("/api/v1/posts/by/user-01?limit=2")
    assert response.status_code == 200
    assert len(response.json()) == 2


async def test_list_replies(client: AsyncClient, context) -> None:
    headers = _auth_header(context.codec, "user-01")
    create = await client.post(
        "/api/v1/posts", json={"text": "parent"}, headers=headers
    )
    parent_id = create.json()["id"]

    await client.post(
        "/api/v1/posts",
        json={"text": "reply 1", "reply_to_id": parent_id},
        headers=headers,
    )
    await client.post(
        "/api/v1/posts",
        json={"text": "reply 2", "reply_to_id": parent_id},
        headers=headers,
    )

    response = await client.get(f"/api/v1/posts/{parent_id}/replies")
    assert response.status_code == 200
    assert len(response.json()) == 2


async def test_reply_increments_reply_count(client: AsyncClient, context) -> None:
    headers = _auth_header(context.codec, "user-01")
    create = await client.post(
        "/api/v1/posts", json={"text": "parent"}, headers=headers
    )
    parent_id = create.json()["id"]

    await client.post(
        "/api/v1/posts",
        json={"text": "reply", "reply_to_id": parent_id},
        headers=headers,
    )

    get_resp = await client.get(f"/api/v1/posts/{parent_id}")
    assert get_resp.json()["replies_count"] == 1


async def test_create_post_requires_auth(client: AsyncClient) -> None:
    response = await client.post("/api/v1/posts", json={"text": "no auth"})
    assert response.status_code == 401


async def test_create_post_requires_text(client: AsyncClient, context) -> None:
    headers = _auth_header(context.codec, "user-01")
    response = await client.post("/api/v1/posts", json={"text": ""}, headers=headers)
    assert response.status_code == 422


async def test_create_post_with_media_ids(client: AsyncClient, context) -> None:
    headers = _auth_header(context.codec, "user-01")
    response = await client.post(
        "/api/v1/posts",
        json={"text": "with media", "media_ids": ["media-01", "media-02"]},
        headers=headers,
    )
    assert response.status_code == 201
    assert len(response.json()["media_ids"]) == 2
