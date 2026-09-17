"""Composition root and FastAPI dependencies.

Everything with a lifetime longer than a request (engine, Redis client, HTTP
clients, JWT codec) is built once in `ServiceContext.create` and torn down in
`ServiceContext.close`. Handlers receive collaborators through `Depends`, so a
test can build a context over an in-memory bus and a throwaway database
without patching module globals.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Annotated

import redis.asyncio as redis
from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from chirp_common.auth.deps import AuthenticatedUser, build_auth_dependencies
from chirp_common.auth.jwt import JWTCodec
from chirp_common.db.session import Database
from chirp_common.events.bus import EventBus
from chirp_common.events.worker import build_event_bus
from chirp_common.http.client import ServiceClient
from chirp_common.ratelimit import NullRateLimiter, RateLimiter, RedisRateLimiter
from app.repository import AccountRepository, SessionRepository
from app.service import AuthService
from app.settings import AuthSettings


@dataclass(slots=True)
class ServiceContext:
    settings: AuthSettings
    database: Database
    bus: EventBus
    codec: JWTCodec
    user_client: ServiceClient
    rate_limiter: RateLimiter
    redis_client: redis.Redis | None

    @classmethod
    def create(cls, settings: AuthSettings) -> "ServiceContext":
        redis_client: redis.Redis | None = None
        rate_limiter: RateLimiter = NullRateLimiter()
        if settings.environment != "test":
            redis_client = redis.from_url(
                settings.redis_url,
                decode_responses=True,
                socket_timeout=settings.redis_timeout_seconds,
            )
            rate_limiter = RedisRateLimiter(redis_client)

        return cls(
            settings=settings,
            database=Database(settings),
            bus=build_event_bus(settings, service_name=settings.service_name),
            codec=JWTCodec(
                secret=settings.jwt_secret,
                algorithm=settings.jwt_algorithm,
                issuer=settings.jwt_issuer,
                audience=settings.jwt_audience,
                access_ttl_seconds=settings.access_token_ttl_seconds,
            ),
            user_client=ServiceClient(
                base_url=settings.user_service_url,
                dependency="user-service",
                service_name=settings.service_name,
                timeout_seconds=settings.http_timeout_seconds,
                connect_timeout_seconds=settings.http_connect_timeout_seconds,
                max_retries=settings.http_max_retries,
            ),
            rate_limiter=rate_limiter,
            redis_client=redis_client,
        )

    async def close(self) -> None:
        await self.user_client.aclose()
        await self.bus.close()
        await self.database.dispose()
        if self.redis_client is not None:
            await self.redis_client.aclose()


def get_context(request: Request) -> ServiceContext:
    return request.app.state.context


Context = Annotated[ServiceContext, Depends(get_context)]


async def get_session(context: Context) -> AsyncIterator[AsyncSession]:
    async with context.database.session() as session:
        yield session


DbSession = Annotated[AsyncSession, Depends(get_session)]


def get_auth_service(context: Context, session: DbSession) -> AuthService:
    return AuthService(
        db=session,
        accounts=AccountRepository(session),
        sessions=SessionRepository(session),
        codec=context.codec,
        settings=context.settings,
        user_client=context.user_client,
        bus=context.bus,
    )


Auth = Annotated[AuthService, Depends(get_auth_service)]


def _current_user(request: Request) -> AuthenticatedUser:
    required, _ = build_auth_dependencies(get_context(request).codec)
    return required(request)


CurrentUser = Annotated[AuthenticatedUser, Depends(_current_user)]


def client_ip(request: Request) -> str | None:
    """Prefer the gateway-set forwarded address over the socket peer.

    Only trusted because in this topology nothing but the gateway can reach
    the service; a public-facing deployment must strip and re-set this header
    at the edge.
    """
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None
