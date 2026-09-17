from __future__ import annotations

from httpx import AsyncClient

from chirp_common.events.envelope import EventType
from tests.conftest import auth_header


async def test_create_report(client: AsyncClient, context, bus) -> None:
    headers = auth_header(context.codec, "user-01")
    response = await client.post(
        "/api/v1/moderation/reports",
        json={
            "target_type": "post",
            "target_id": "post-123",
            "reason": "Spam content",
        },
        headers=headers,
    )
    assert response.status_code == 201
    body = response.json()
    assert body["state"] == "pending"
    assert body["reporter_id"] == "user-01"

    published = bus.published_of(EventType.REPORT_CREATED)
    assert len(published) == 1


async def test_create_report_requires_auth(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/moderation/reports",
        json={"target_type": "post", "target_id": "x", "reason": "x"},
    )
    assert response.status_code == 401


async def test_list_reports_requires_admin(client: AsyncClient, context) -> None:
    headers = auth_header(context.codec, "user-01")
    response = await client.get("/api/v1/moderation/reports", headers=headers)
    assert response.status_code == 403


async def test_list_reports_as_admin(client: AsyncClient, context) -> None:
    headers = auth_header(context.codec, "admin-01", scopes=("admin",))
    response = await client.get("/api/v1/moderation/reports", headers=headers)
    assert response.status_code == 200
    assert response.json()["reports"] == []


async def test_review_report_requires_admin(client: AsyncClient, context) -> None:
    headers = auth_header(context.codec, "user-01")
    response = await client.post(
        "/api/v1/moderation/reports/report-123/review",
        json={"resolution": "Reviewed"},
        headers=headers,
    )
    assert response.status_code == 403


async def test_take_action_requires_admin(client: AsyncClient, context) -> None:
    headers = auth_header(context.codec, "user-01")
    response = await client.post(
        "/api/v1/moderation/actions",
        json={
            "action_type": "delete",
            "target_type": "post",
            "target_id": "post-123",
            "reason": "Violation",
        },
        headers=headers,
    )
    assert response.status_code == 403


async def test_admin_can_take_action(client: AsyncClient, context, bus) -> None:
    headers = auth_header(context.codec, "admin-01", scopes=("admin",))
    response = await client.post(
        "/api/v1/moderation/actions",
        json={
            "action_type": "delete",
            "target_type": "post",
            "target_id": "post-123",
            "reason": "Violation of terms",
        },
        headers=headers,
    )
    assert response.status_code == 201
    published = bus.published_of(EventType.CONTENT_ACTIONED)
    assert len(published) == 1


async def test_create_report_with_different_target_types(
    client: AsyncClient, context
) -> None:
    headers = auth_header(context.codec, "user-01")
    for target_type in ["post", "user", "message"]:
        response = await client.post(
            "/api/v1/moderation/reports",
            json={
                "target_type": target_type,
                "target_id": "target-01",
                "reason": f"Report for {target_type}",
            },
            headers=headers,
        )
        assert response.status_code == 201
        assert response.json()["target_type"] == target_type
