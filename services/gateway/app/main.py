"""Gateway service entrypoint."""

from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import FastAPI

from chirp_common.http.app import HealthCheck, create_app
from app.dependencies import ServiceContext
from app.routes import router
from app.settings import get_settings


def build_app() -> FastAPI:
    settings = get_settings()
    context = ServiceContext.create(settings)

    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.context = context
        try:
            yield
        finally:
            await context.close()

    async def _ping_auth() -> bool:
        return await context.clients.auth.ping()

    async def _ping_user() -> bool:
        return await context.clients.user.ping()

    async def _ping_post() -> bool:
        return await context.clients.post.ping()

    async def _ping_timeline() -> bool:
        return await context.clients.timeline.ping()

    async def _ping_graph() -> bool:
        return await context.clients.graph.ping()

    async def _ping_search() -> bool:
        return await context.clients.search.ping()

    async def _ping_notification() -> bool:
        return await context.clients.notification.ping()

    async def _ping_messaging() -> bool:
        return await context.clients.messaging.ping()

    async def _ping_media() -> bool:
        return await context.clients.media.ping()

    async def _ping_moderation() -> bool:
        return await context.clients.moderation.ping()

    app = create_app(
        settings=settings,
        title="Chirp Gateway Service",
        description="API gateway and BFF for Chirp.",
        lifespan=lifespan,
        readiness_checks=[
            HealthCheck("auth-service", _ping_auth, critical=True),
            HealthCheck("user-service", _ping_user, critical=True),
            HealthCheck("post-service", _ping_post, critical=True),
            HealthCheck("timeline-service", _ping_timeline, critical=True),
            HealthCheck("graph-service", _ping_graph, critical=False),
            HealthCheck("search-service", _ping_search, critical=False),
            HealthCheck("notification-service", _ping_notification, critical=False),
            HealthCheck("messaging-service", _ping_messaging, critical=False),
            HealthCheck("media-service", _ping_media, critical=False),
            HealthCheck("moderation-service", _ping_moderation, critical=False),
        ],
    )
    app.include_router(router)
    return app


app = build_app()
