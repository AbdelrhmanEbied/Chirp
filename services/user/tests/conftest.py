from __future__ import annotations

import os
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from chirp_common.auth.jwt import JWTCodec
from chirp_common.cache import NullCache
from chirp_common.db.base import Base
from chirp_common.db.session import Database
from chirp_common.events.memory import InMemoryEventBus
from chirp_common.http.app import create_app
from chirp_common.testing.factories import TEST_JWT_SECRET
from app import models  # noqa: F401 - registers tables
from app.dependencies import ServiceContext
from app.routes import internal_router, router
from app.settings import UserSettings

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "sqlite+aiosqlite:///:memory:")


@pytest.fixture
def settings() -> UserSettings:
    return UserSettings(
        service_name="user-service-test",
        environment="test",
        jwt_secret=TEST_JWT_SECRET,
        database_url=TEST_DATABASE_URL,
        event_bus_backend="memory",
        cache_enabled=False,
        log_json=False,
        username_change_cooldown_days=30,
    )


@pytest_asyncio.fixture
async def context(settings: UserSettings) -> AsyncIterator[ServiceContext]:
    database = Database(settings)
    async with database.engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    ctx = ServiceContext(
        settings=settings,
        database=database,
        bus=InMemoryEventBus(settings.service_name),
        cache=NullCache(),
        codec=JWTCodec(
            secret=settings.jwt_secret,
            issuer=settings.jwt_issuer,
            audience=settings.jwt_audience,
        ),
        redis_client=None,
    )
    yield ctx
    await database.dispose()


@pytest_asyncio.fixture
async def client(context: ServiceContext) -> AsyncIterator[AsyncClient]:
    app = create_app(settings=context.settings, title="user-test")
    app.state.context = context
    app.include_router(router)
    app.include_router(internal_router)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://user.test"
    ) as http:
        yield http


@pytest.fixture
def bus(context: ServiceContext) -> InMemoryEventBus:
    return context.bus  # type: ignore[return-value]


@pytest.fixture
def token(context: ServiceContext):
    def _issue(user_id: str, *, admin: bool = False) -> dict[str, str]:
        access, _ = context.codec.issue_access_token(
            user_id=user_id, session_id="test-session", scopes=("admin",) if admin else ()
        )
        return {"authorization": f"Bearer {access}"}

    return _issue


ADA_ID = "01J0000000000000000000ADA0"


@pytest_asyncio.fixture
async def ada(client: AsyncClient) -> dict:
    response = await client.post(
        "/internal/v1/users",
        json={"user_id": ADA_ID, "username": "ada", "display_name": "Ada Lovelace"},
    )
    assert response.status_code == 201, response.text
    return response.json()
