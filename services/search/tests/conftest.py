"""Test fixtures for the search service."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from chirp_common.db.base import Base
from chirp_common.db.session import Database
from chirp_common.events.memory import InMemoryEventBus
from chirp_common.testing.factories import TEST_JWT_SECRET
from app import models  # noqa: F401
from app.dependencies import ServiceContext
from app.routes import router
from app.settings import SearchSettings

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "sqlite+aiosqlite:///:memory:")


@pytest.fixture
def settings() -> SearchSettings:
    return SearchSettings(
        service_name="search-service-test",
        environment="test",
        jwt_secret=TEST_JWT_SECRET,
        database_url=TEST_DATABASE_URL,
        event_bus_backend="memory",
        log_json=False,
    )


@pytest_asyncio.fixture
async def context(settings: SearchSettings) -> AsyncIterator[ServiceContext]:
    database = Database(settings)
    async with database.engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    ctx = ServiceContext(
        settings=settings,
        database=database,
        bus=InMemoryEventBus(settings.service_name),
    )
    yield ctx
    await database.dispose()


@pytest_asyncio.fixture
async def client(context: ServiceContext) -> AsyncIterator[AsyncClient]:
    from chirp_common.http.app import create_app
    app = create_app(settings=context.settings, title="search-test")
    app.state.context = context
    app.include_router(router)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://search.test") as http:
        yield http


@pytest.fixture
def bus(context: ServiceContext) -> InMemoryEventBus:
    return context.bus  # type: ignore[return-value]
