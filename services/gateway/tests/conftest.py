"""Test fixtures for the gateway service."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from typing import Any

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from chirp_common.auth.jwt import JWTCodec
from chirp_common.testing.factories import TEST_JWT_SECRET
from app.dependencies import ServiceContext, ServiceClients
from app.routes import router
from app.settings import GatewaySettings


class FakeServiceClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self._response: Any = None

    def set_response(self, response: Any) -> None:
        self._response = response

    async def request(self, method: str, path: str, **kwargs: Any) -> Any:
        self.calls.append({"method": method, "path": path, **kwargs})
        return self._response

    async def get(self, path: str, **kwargs: Any) -> Any:
        return await self.request("GET", path, **kwargs)

    async def post(self, path: str, **kwargs: Any) -> Any:
        return await self.request("POST", path, **kwargs)

    async def ping(self) -> bool:
        return True

    async def aclose(self) -> None:
        return None


@pytest.fixture
def settings() -> GatewaySettings:
    return GatewaySettings(
        service_name="gateway-test",
        environment="test",
        jwt_secret=TEST_JWT_SECRET,
        event_bus_backend="memory",
        log_json=False,
    )


@pytest.fixture
def context(settings: GatewaySettings) -> ServiceContext:
    auth_client = FakeServiceClient()
    user_client = FakeServiceClient()
    post_client = FakeServiceClient()
    graph_client = FakeServiceClient()
    timeline_client = FakeServiceClient()
    search_client = FakeServiceClient()
    notification_client = FakeServiceClient()
    messaging_client = FakeServiceClient()
    media_client = FakeServiceClient()
    moderation_client = FakeServiceClient()

    clients = ServiceClients(
        auth=auth_client,  # type: ignore[arg-type]
        user=user_client,  # type: ignore[arg-type]
        post=post_client,  # type: ignore[arg-type]
        graph=graph_client,  # type: ignore[arg-type]
        timeline=timeline_client,  # type: ignore[arg-type]
        search=search_client,  # type: ignore[arg-type]
        notification=notification_client,  # type: ignore[arg-type]
        messaging=messaging_client,  # type: ignore[arg-type]
        media=media_client,  # type: ignore[arg-type]
        moderation=moderation_client,  # type: ignore[arg-type]
    )

    ctx = ServiceContext(
        settings=settings,
        clients=clients,
        codec=JWTCodec(
            secret=settings.jwt_secret,
            issuer=settings.jwt_issuer,
            audience=settings.jwt_audience,
            access_ttl_seconds=settings.access_token_ttl_seconds,
        ),
        rate_limiter=None,
    )
    ctx._fake_clients = {  # type: ignore[attr-defined]
        "auth": auth_client,
        "user": user_client,
        "post": post_client,
        "graph": graph_client,
        "timeline": timeline_client,
        "search": search_client,
        "notification": notification_client,
        "messaging": messaging_client,
        "media": media_client,
        "moderation": moderation_client,
    }
    return ctx


@pytest_asyncio.fixture
async def client(context: ServiceContext) -> AsyncIterator[AsyncClient]:
    from chirp_common.http.app import create_app
    app = create_app(settings=context.settings, title="gateway-test")
    app.state.context = context
    app.include_router(router)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://gateway.test") as http:
        yield http


def auth_header(codec: JWTCodec, user_id: str, *, scopes: tuple[str, ...] = ()) -> dict[str, str]:
    token, _ = codec.issue_access_token(user_id=user_id, session_id="test-session", scopes=scopes)
    return {"authorization": f"Bearer {token}"}
