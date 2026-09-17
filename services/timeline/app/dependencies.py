"""Timeline service dependencies."""

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
from app.repository import TimelineRepository
from app.service import TimelineService
from app.settings import TimelineSettings


@dataclass(slots=True)
class ServiceContext:
    settings: TimelineSettings
    database: Database
    bus: EventBus
    codec: JWTCodec
    redis_client: redis.Redis | None
    post_client: ServiceClient
    graph_client: ServiceClient
    user_client: ServiceClient

    @classmethod
    def create(cls, settings: TimelineSettings) -> "ServiceContext":
        redis_client: redis.Redis | None = None
        if settings.cache_enabled and settings.environment != "test":
            redis_client = redis.from_url(
                settings.redis_url,
                decode_responses=True,
                socket_timeout=settings.redis_timeout_seconds,
                socket_connect_timeout=2,
                max_connections=20,
            )
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
            redis_client=redis_client,
            post_client=ServiceClient(
                base_url=settings.post_service_url,
                dependency="post-service",
                service_name=settings.service_name,
                timeout_seconds=settings.http_timeout_seconds,
                connect_timeout_seconds=settings.http_connect_timeout_seconds,
                max_retries=settings.http_max_retries,
            ),
            graph_client=ServiceClient(
                base_url=settings.graph_service_url,
                dependency="graph-service",
                service_name=settings.service_name,
                timeout_seconds=settings.http_timeout_seconds,
                connect_timeout_seconds=settings.http_connect_timeout_seconds,
                max_retries=settings.http_max_retries,
            ),
            user_client=ServiceClient(
                base_url=settings.user_service_url,
                dependency="user-service",
                service_name=settings.service_name,
                timeout_seconds=settings.http_timeout_seconds,
                connect_timeout_seconds=settings.http_connect_timeout_seconds,
                max_retries=settings.http_max_retries,
            ),
        )

    async def close(self) -> None:
        await self.bus.close()
        await self.database.dispose()
        await self.post_client.aclose()
        await self.graph_client.aclose()
        await self.user_client.aclose()
        if self.redis_client is not None:
            await self.redis_client.aclose()


def get_context(request: Request) -> ServiceContext:
    return request.app.state.context


Context = Annotated[ServiceContext, Depends(get_context)]


async def get_session(context: Context) -> AsyncIterator[AsyncSession]:
    async with context.database.session() as session:
        yield session


DbSession = Annotated[AsyncSession, Depends(get_session)]


def get_timeline_repository(context: Context, session: DbSession) -> TimelineRepository:
    return TimelineRepository(
        session=session,
        post_client=context.post_client,
        user_client=context.user_client,
        max_feed_size=context.settings.max_feed_size,
    )


def get_timeline_service(context: Context, repo: Annotated[TimelineRepository, Depends(get_timeline_repository)]) -> TimelineService:
    return TimelineService(
        repository=repo,
        user_client=context.user_client,
        settings=context.settings,
    )


Timeline = Annotated[TimelineService, Depends(get_timeline_service)]


def _current_user(request: Request) -> AuthenticatedUser:
    required, _ = build_auth_dependencies(get_context(request).codec)
    return required(request)


CurrentUser = Annotated[AuthenticatedUser, Depends(_current_user)]
