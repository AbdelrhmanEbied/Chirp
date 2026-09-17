"""Test fixtures for the graph service."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from chirp_common.db.base import Base
from chirp_common.db.session import Database
from chirp_common.events.memory import InMemoryEventBus
from chirp_common.auth.jwt import JWTCodec
from chirp_common.testing.factories import TEST_JWT_SECRET
from app import models  # noqa: F401
from app.dependencies import ServiceContext
from app.routes import router, internal_router
from app.settings import GraphSettings

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "sqlite+aiosqlite:///:memory:")


@pytest.fixture
def settings() -> GraphSettings:
    return GraphSettings(
        service_name="graph-service-test",
        environment="test",
        jwt_secret=TEST_JWT_SECRET,
        database_url=TEST_DATABASE_URL,
        event_bus_backend="memory",
        log_json=False,
    )


@pytest_asyncio.fixture
async def context(settings: GraphSettings) -> AsyncIterator[ServiceContext]:
    database = Database(settings)
    async with database.engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    ctx = ServiceContext(
        settings=settings,
        database=database,
        bus=InMemoryEventBus(settings.service_name),
        codec=JWTCodec(
            secret=settings.jwt_secret,
            issuer=settings.jwt_issuer,
            audience=settings.jwt_audience,
            access_ttl_seconds=settings.access_token_ttl_seconds,
        ),
        redis_client=None,
    )
    yield ctx
    await database.dispose()


@pytest_asyncio.fixture
async def client(context: ServiceContext) -> AsyncIterator[AsyncClient]:
    from chirp_common.http.app import create_app
    app = create_app(settings=context.settings, title="graph-test")
    app.state.context = context
    app.include_router(router)
    app.include_router(internal_router)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://graph.test") as http:
        yield http


@pytest.fixture
def bus(context: ServiceContext) -> InMemoryEventBus:
    return context.bus  # type: ignore[return-value]


def auth_header(codec: JWTCodec, user_id: str) -> dict[str, str]:
    token, _ = codec.issue_access_token(user_id=user_id, session_id="test-session")
    return {"authorization": f"Bearer {token}"}
