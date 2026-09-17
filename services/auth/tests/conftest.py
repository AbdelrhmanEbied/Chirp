"""Test fixtures for the auth service.

The suite runs against SQLite by default so `make test` needs no containers.
Set `TEST_DATABASE_URL=postgresql+asyncpg://...` to run the same tests against
PostgreSQL, which is what `make test-integration` does inside Compose. Any test
that depends on PostgreSQL-specific behaviour is marked `requires_postgres`.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from typing import Any

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from chirp_common.db.base import Base
from chirp_common.db.session import Database
from chirp_common.events.memory import InMemoryEventBus
from chirp_common.http.app import create_app
from chirp_common.auth.jwt import JWTCodec
from chirp_common.ratelimit import NullRateLimiter
from chirp_common.testing.factories import TEST_JWT_SECRET
from app import models  # noqa: F401 - registers tables on the metadata
from app.dependencies import ServiceContext
from app.routes import router
from app.settings import AuthSettings

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "sqlite+aiosqlite:///:memory:")


class FakeUserClient:
    """Stands in for the user service.

    `created` records the calls so tests can assert the registration
    handshake happened, and `failure` lets a test simulate the user service
    rejecting a duplicate username.
    """

    def __init__(self) -> None:
        self.created: list[dict[str, Any]] = []
        self.failure: Exception | None = None

    async def request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        if self.failure is not None:
            raise self.failure
        payload = kwargs.get("json") or {}
        self.created.append(payload)
        return {"id": payload.get("user_id"), "username": payload.get("username")}

    async def ping(self) -> bool:
        return True

    async def aclose(self) -> None:
        return None


@pytest.fixture
def settings() -> AuthSettings:
    return AuthSettings(
        service_name="auth-service-test",
        environment="test",
        jwt_secret=TEST_JWT_SECRET,
        database_url=TEST_DATABASE_URL,
        event_bus_backend="memory",
        log_json=False,
        access_token_ttl_seconds=900,
        max_active_sessions_per_user=3,
    )


@pytest_asyncio.fixture
async def context(settings: AuthSettings) -> AsyncIterator[ServiceContext]:
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
        user_client=FakeUserClient(),  # type: ignore[arg-type]
        rate_limiter=NullRateLimiter(),
        redis_client=None,
    )
    yield ctx
    await database.dispose()


@pytest_asyncio.fixture
async def client(context: ServiceContext) -> AsyncIterator[AsyncClient]:
    from chirp_common.http.app import HealthCheck
    app = create_app(
        settings=context.settings,
        title="auth-test",
        readiness_checks=[
            HealthCheck("database", context.database.check, critical=True),
            HealthCheck("user-service", context.user_client.ping, critical=False),
        ],
    )
    app.state.context = context
    app.include_router(router)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://auth.test") as http:
        yield http


@pytest.fixture
def bus(context: ServiceContext) -> InMemoryEventBus:
    return context.bus  # type: ignore[return-value]


@pytest.fixture
def user_client(context: ServiceContext) -> FakeUserClient:
    return context.user_client  # type: ignore[return-value]


REGISTRATION = {
    "email": "ada@example.com",
    "username": "ada",
    "display_name": "Ada Lovelace",
    "password": "analytical-engine-1843",
}


@pytest_asyncio.fixture
async def registered(client: AsyncClient) -> dict[str, Any]:
    response = await client.post("/api/v1/auth/register", json=REGISTRATION)
    assert response.status_code == 201, response.text
    return response.json()
