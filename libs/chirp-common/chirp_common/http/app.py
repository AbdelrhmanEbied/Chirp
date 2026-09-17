"""FastAPI application factory.

Every Chirp service calls `create_app`. That is what makes the services
consistent without a framework of our own: identical middleware order,
identical error envelope, identical health and metrics endpoints, identical
OpenAPI conventions.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass, field

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from starlette.exceptions import HTTPException as StarletteHTTPException

from chirp_common import context
from chirp_common.config import ServiceSettings
from chirp_common.errors import AppError, RateLimitedError
from chirp_common.http.middleware import (
    AccessLogMiddleware,
    BodySizeLimitMiddleware,
    RequestContextMiddleware,
)
from chirp_common.logging import configure_logging
from chirp_common.metrics import REGISTRY

log = logging.getLogger(__name__)

Lifespan = Callable[[FastAPI], "AsyncIterator[None]"]


@dataclass(slots=True)
class HealthCheck:
    """A readiness dependency.

    `critical=True` means the service cannot serve correct responses without
    it and should fail readiness (Kubernetes pulls it from the load balancer
    but does not restart it). Non-critical dependencies -- typically the cache
    -- are reported but do not fail the probe, because degraded is better than
    removed.
    """

    name: str
    probe: Callable[[], Awaitable[bool]]
    critical: bool = True


@dataclass(slots=True)
class AppState:
    readiness: list[HealthCheck] = field(default_factory=list)


def create_app(
    *,
    settings: ServiceSettings,
    title: str,
    description: str = "",
    version: str = "0.1.0",
    lifespan: Callable[[FastAPI], "AsyncIterator[None]"] | None = None,
    readiness_checks: Sequence[HealthCheck] = (),
) -> FastAPI:
    configure_logging(settings.service_name, settings.log_level, json=settings.log_json)

    @asynccontextmanager
    async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
        log.info(
            "service starting",
            extra={"service": settings.service_name, "environment": settings.environment},
        )
        if lifespan is None:
            yield
        else:
            async with asynccontextmanager(lifespan)(app):
                yield
        log.info("service stopped", extra={"service": settings.service_name})

    app = FastAPI(
        title=title,
        description=description,
        version=version,
        lifespan=_lifespan,
        docs_url="/docs",
        redoc_url=None,
        openapi_url="/openapi.json",
        # Errors are documented once here rather than on every route.
        responses={
            400: {"description": "Malformed request"},
            401: {"description": "Missing or invalid access token"},
            403: {"description": "Authenticated but not permitted"},
            404: {"description": "Resource does not exist"},
            422: {"description": "Request failed validation"},
            429: {"description": "Rate limited"},
        },
    )
    app.state.chirp = AppState(readiness=list(readiness_checks))
    app.state.settings = settings

    # Added innermost-first: the last `add_middleware` call is the outermost
    # layer, so CORS wraps everything and request ids are bound before the
    # access log and the route run.
    app.add_middleware(AccessLogMiddleware, service_name=settings.service_name)
    app.add_middleware(BodySizeLimitMiddleware, max_bytes=settings.request_max_bytes)
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["authorization", "content-type", context.CORRELATION_ID_HEADER],
        expose_headers=[context.REQUEST_ID_HEADER, context.CORRELATION_ID_HEADER],
        max_age=600,
    )

    _install_exception_handlers(app, settings)
    _install_operational_routes(app, settings)
    return app


def _install_exception_handlers(app: FastAPI, settings: ServiceSettings) -> None:
    @app.exception_handler(AppError)
    async def _app_error(request: Request, exc: AppError) -> JSONResponse:
        if exc.status_code >= 500:
            log.error("request failed", exc_info=exc, extra={"code": exc.code})
        else:
            log.info("request rejected", extra={"code": exc.code, "status": exc.status_code})
        headers = {}
        if isinstance(exc, RateLimitedError):
            headers["Retry-After"] = str(exc.retry_after_seconds)
        return JSONResponse(
            status_code=exc.status_code,
            content=exc.to_payload(context.get_request_id()),
            headers=headers,
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        details = [
            {
                "field": ".".join(str(part) for part in err.get("loc", ())[1:]),
                "message": err.get("msg", "invalid value"),
                "type": err.get("type", "value_error"),
            }
            for err in exc.errors()
        ]
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "validation_error",
                    "message": "The request failed validation.",
                    "details": {"fields": details},
                    "request_id": context.get_request_id(),
                }
            },
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(
        request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        codes = {404: "not_found", 405: "method_not_allowed", 401: "unauthorized"}
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": codes.get(exc.status_code, "http_error"),
                    "message": str(exc.detail),
                    "request_id": context.get_request_id(),
                }
            },
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        # The real exception goes to the logs only. Returning it to the client
        # leaks stack traces, query fragments and internal hostnames.
        log.exception(
            "unhandled exception",
            extra={"service": settings.service_name, "path": request.url.path},
        )
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "internal_error",
                    "message": "Internal server error.",
                    "request_id": context.get_request_id(),
                }
            },
        )


def _install_operational_routes(app: FastAPI, settings: ServiceSettings) -> None:
    @app.get("/health/live", tags=["operations"], include_in_schema=False)
    async def liveness() -> dict[str, str]:
        """Is the process alive? Never touches dependencies.

        A liveness probe that checks the database restarts every pod during a
        database blip, which turns a recoverable incident into an outage.
        """
        return {"status": "ok", "service": settings.service_name}

    @app.get("/health/ready", tags=["operations"], include_in_schema=False)
    async def readiness() -> JSONResponse:
        """Can this instance serve traffic right now?"""
        results: dict[str, str] = {}
        ready = True
        for check in app.state.chirp.readiness:
            try:
                healthy = await check.probe()
            except Exception:  # noqa: BLE001 - a probe must never raise out
                log.warning("readiness probe raised", extra={"check": check.name})
                healthy = False
            results[check.name] = "ok" if healthy else "failing"
            if not healthy and check.critical:
                ready = False
        return JSONResponse(
            status_code=200 if ready else 503,
            content={
                "status": "ready" if ready else "not_ready",
                "service": settings.service_name,
                "checks": results,
            },
        )

    if settings.metrics_enabled:

        @app.get("/metrics", tags=["operations"], include_in_schema=False)
        async def metrics() -> PlainTextResponse:
            return PlainTextResponse(
                generate_latest(REGISTRY), media_type=CONTENT_TYPE_LATEST
            )
