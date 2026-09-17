"""Graph service entrypoint."""

from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import FastAPI

from chirp_common.http.app import HealthCheck, create_app
from app.dependencies import ServiceContext
from app.routes import internal_router, router
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

    app = create_app(
        settings=settings,
        title="Chirp Graph Service",
        description=(
            "Manages the social graph: follows, blocks and mutes between users."
        ),
        lifespan=lifespan,
        readiness_checks=[HealthCheck("database", context.database.check, critical=True)],
    )
    app.include_router(router)
    app.include_router(internal_router)
    return app


app = build_app()
