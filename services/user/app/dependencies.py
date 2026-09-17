from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Annotated

import redis.asyncio as redis
from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from chirp_common.auth.deps import AuthenticatedUser, build_auth_dependencies
from chirp_common.auth.jwt import JWTCodec
from chirp_common.cache import Cache, NullCache, RedisCache
from chirp_common.db.session import Database
from chirp_common.events.bus import EventBus
from chirp_common.events.worker import build_event_bus
from app.repository import ProfileRepository
from app.service import UserService
from app.settings import UserSettings


@dataclass(slots=True)
class ServiceContext:
    settings: UserSettings
    database: Database
    bus: EventBus
    cache: Cache
    codec: JWTCodec
    redis_client: redis.Redis | None

    @classmethod
    def create(cls, settings: UserSettings) -> "ServiceContext":
        redis_client: redis.Redis | None = None
        cache: Cache = NullCache()
        if settings.cache_enabled and settings.environment != "test":
            redis_client = redis.from_url(
                settings.redis_url,
                decode_responses=True,
                socket_timeout=settings.redis_timeout_seconds,
            )
            cache = RedisCache(
                redis_client,
                service=settings.service_name,
                namespace="profile",
                default_ttl_seconds=settings.profile_cache_ttl_seconds,
            )
        return cls(
            settings=settings,
            database=Database(settings),
            bus=build_event_bus(settings, service_name=settings.service_name),
            cache=cache,
            codec=JWTCodec(
                secret=settings.jwt_secret,
                algorithm=settings.jwt_algorithm,
                issuer=settings.jwt_issuer,
                audience=settings.jwt_audience,
                access_ttl_seconds=settings.access_token_ttl_seconds,
            ),
            redis_client=redis_client,
        )

    async def close(self) -> None:
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


def get_user_service(context: Context, session: DbSession) -> UserService:
    return UserService(
        db=session,
        profiles=ProfileRepository(session),
        cache=context.cache,
        bus=context.bus,
        settings=context.settings,
    )


Users = Annotated[UserService, Depends(get_user_service)]


def _current_user(request: Request) -> AuthenticatedUser:
    required, _ = build_auth_dependencies(get_context(request).codec)
    return required(request)


CurrentUser = Annotated[AuthenticatedUser, Depends(_current_user)]
