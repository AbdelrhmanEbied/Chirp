from __future__ import annotations

from httpx import AsyncClient


async def test_liveness_never_touches_dependencies(client: AsyncClient) -> None:
    response = await client.get("/health/live")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


async def test_metrics_endpoint_is_scrapeable(client: AsyncClient) -> None:
    await client.get("/health/live")
    response = await client.get("/metrics")
    assert response.status_code == 200
    assert "chirp_http_requests_total" in response.text


async def test_request_id_is_echoed(client: AsyncClient) -> None:
    response = await client.get("/health/live", headers={"x-request-id": "abc123"})
    assert response.headers["x-request-id"] == "abc123"
    assert response.headers["x-correlation-id"] == "abc123"


async def test_openapi_document_is_generated(client: AsyncClient) -> None:
    response = await client.get("/openapi.json")
    assert response.status_code == 200
    assert "/api/v1/auth/login" in response.json()["paths"]
