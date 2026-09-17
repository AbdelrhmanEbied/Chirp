from __future__ import annotations

from httpx import AsyncClient

from chirp_common.events.envelope import EventType
from tests.conftest import auth_header


async def test_upload_requires_auth(client: AsyncClient) -> None:
    response = await client.post("/api/v1/media")
    assert response.status_code == 401


async def test_get_nonexistent_media_returns_404(
    client: AsyncClient, context
) -> None:
    headers = auth_header(context.codec, "user-01")
    response = await client.get(
        "/api/v1/media/00000000000000000000000000", headers=headers
    )
    assert response.status_code == 404


async def test_delete_nonexistent_media_returns_404(
    client: AsyncClient, context
) -> None:
    headers = auth_header(context.codec, "user-01")
    response = await client.delete(
        "/api/v1/media/00000000000000000000000000", headers=headers
    )
    assert response.status_code == 404


async def test_upload_and_get_media(client: AsyncClient, context) -> None:
    headers = auth_header(context.codec, "user-01")
    # Create a minimal valid PNG (1x1 pixel)
    import base64
    png_data = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
    )

    response = await client.post(
        "/api/v1/media",
        headers=headers,
        content=png_data,
        params={"content_type": "image/png"},
    )
    assert response.status_code == 201
    media_id = response.json()["id"]

    # Get the media
    get_resp = await client.get(f"/api/v1/media/{media_id}", headers=headers)
    assert get_resp.status_code == 200
    assert get_resp.json()["content_type"] == "image/png"


async def test_upload_and_delete_media(client: AsyncClient, context, bus) -> None:
    headers = auth_header(context.codec, "user-01")
    import base64
    png_data = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
    )

    response = await client.post(
        "/api/v1/media",
        headers=headers,
        content=png_data,
        params={"content_type": "image/png"},
    )
    assert response.status_code == 201
    media_id = response.json()["id"]

    delete_resp = await client.delete(f"/api/v1/media/{media_id}", headers=headers)
    assert delete_resp.status_code == 204

    published = bus.published_of(EventType.MEDIA_DELETED)
    assert len(published) == 1
