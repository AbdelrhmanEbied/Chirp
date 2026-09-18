
from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Annotated

import redis.asyncio as redis
from fastapi import Depends, Request

from chirp_common.auth.deps import AuthenticatedUser, build_auth_dependencies
from chirp_common.auth.jwt import JWTCodec
from chirp_common.http.client import ServiceClient
from chirp_common.ratelimit import NullRateLimiter, RateLimiter, RedisRateLimiter
from app.settings import GatewaySettings


@dataclass(slots=True)
class ServiceClients:
    auth: ServiceClient
    user: ServiceClient
    post: ServiceClient
    graph: ServiceClient
    timeline: ServiceClient
    search: ServiceClient
    notification: ServiceClient
    messaging: ServiceClient
    media: ServiceClient
    moderation: ServiceClient

    async def aclose(self) -> None:
        for client in (
            self.auth,
            self.user,
            self.post,
            self.graph,
            self.timeline,
            self.search,
            self.notification,
            self.messaging,
            self.media,
            self.moderation,
        ):
            await client.aclose()

    async def pings(self) -> dict[str, bool]:
        return {
            "auth": await self.auth.ping(),
            "user": await self.user.ping(),
            "post": await self.post.ping(),
            "graph": await self.graph.ping(),
            "timeline": await self.timeline.ping(),
            "search": await self.search.ping(),
            "notification": await self.notification.ping(),
            "messaging": await self.messaging.ping(),
            "media": await self.media.ping(),
            "moderation": await self.moderation.ping(),
        }


@dataclass(slots=True)
class ServiceContext:
    settings: GatewaySettings
    clients: ServiceClients
    codec: JWTCodec
    rate_limiter: RateLimiter
    redis_client: redis.Redis | None

    @classmethod
    def create(cls, settings: GatewaySettings) -> "ServiceContext":
        http_kw = dict(
            timeout_seconds=settings.http_timeout_seconds,
            connect_timeout_seconds=settings.http_connect_timeout_seconds,
            max_retries=settings.http_max_retries,
        )
        service_name = settings.service_name

        clients = ServiceClients(
            auth=ServiceClient(
                base_url=settings.auth_service_url,
                dependency="auth-service",
                service_name=service_name,
                **http_kw,
            ),
            user=ServiceClient(
                base_url=settings.user_service_url,
                dependency="user-service",
                service_name=service_name,
                **http_kw,
            ),
            post=ServiceClient(
                base_url=settings.post_service_url,
                dependency="post-service",
                service_name=service_name,
                **http_kw,
            ),
            graph=ServiceClient(
                base_url=settings.graph_service_url,
                dependency="graph-service",
                service_name=service_name,
                **http_kw,
            ),
            timeline=ServiceClient(
                base_url=settings.timeline_service_url,
                dependency="timeline-service",
                service_name=service_name,
                **http_kw,
            ),
            search=ServiceClient(
                base_url=settings.search_service_url,
                dependency="search-service",
                service_name=service_name,
                **http_kw,
            ),
            notification=ServiceClient(
                base_url=settings.notification_service_url,
                dependency="notification-service",
                service_name=service_name,
                **http_kw,
            ),
            messaging=ServiceClient(
                base_url=settings.messaging_service_url,
                dependency="messaging-service",
                service_name=service_name,
                **http_kw,
            ),
            media=ServiceClient(
                base_url=settings.media_service_url,
                dependency="media-service",
                service_name=service_name,
                **http_kw,
            ),
            moderation=ServiceClient(
                base_url=settings.moderation_service_url,
                dependency="moderation-service",
                service_name=service_name,
                **http_kw,
            ),
        )

        redis_client: redis.Redis | None = None
        rate_limiter: RateLimiter = NullRateLimiter()
        if settings.environment != "test":
            redis_client = redis.from_url(
                settings.redis_url,
                decode_responses=True,
                socket_timeout=settings.redis_timeout_seconds,
                socket_connect_timeout=2,
                max_connections=20,
            )
            rate_limiter = RedisRateLimiter(redis_client)

        return cls(
            settings=settings,
            clients=clients,
            codec=JWTCodec(
                secret=settings.jwt_secret,
                algorithm=settings.jwt_algorithm,
                issuer=settings.jwt_issuer,
                audience=settings.jwt_audience,
                access_ttl_seconds=settings.access_token_ttl_seconds,
            ),
            rate_limiter=rate_limiter,
            redis_client=redis_client,
        )

    async def close(self) -> None:
        await self.clients.aclose()
        if self.redis_client is not None:
            await self.redis_client.aclose()


def get_context(request: Request) -> ServiceContext:
    return request.app.state.context


Context = Annotated[ServiceContext, Depends(get_context)]


def _current_user(request: Request) -> AuthenticatedUser:
    required, _ = build_auth_dependencies(get_context(request).codec)
    return required(request)


CurrentUser = Annotated[AuthenticatedUser, Depends(_current_user)]


def _optional_user(request: Request) -> AuthenticatedUser | None:
    _, optional = build_auth_dependencies(get_context(request).codec)
    return optional(request)


OptionalUser = Annotated[AuthenticatedUser | None, Depends(_optional_user)]


def client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None
