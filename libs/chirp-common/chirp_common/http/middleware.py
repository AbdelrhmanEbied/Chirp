from __future__ import annotations

import logging
import time

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Match

from chirp_common import context
from chirp_common.metrics import (
    http_request_duration_seconds,
    http_requests_in_flight,
    http_requests_total,
)

log = logging.getLogger("chirp.access")

def route_template(request: Request) -> str:
    for route in request.app.routes:
        match, _ = route.matches(request.scope)
        if match is Match.FULL:
            return getattr(route, "path", request.url.path)
    return "unmatched"

class RequestContextMiddleware(BaseHTTPMiddleware):

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        incoming_request_id = request.headers.get(context.REQUEST_ID_HEADER)
        incoming_correlation_id = request.headers.get(context.CORRELATION_ID_HEADER)

        with context.bind_context(
            request_id=incoming_request_id,
            correlation_id=incoming_correlation_id,
        ) as ctx:
            request.state.request_id = ctx.request_id
            request.state.correlation_id = ctx.correlation_id
            response = await call_next(request)
            response.headers[context.REQUEST_ID_HEADER] = ctx.request_id
            response.headers[context.CORRELATION_ID_HEADER] = ctx.correlation_id
            return response

class AccessLogMiddleware(BaseHTTPMiddleware):

    def __init__(self, app, service_name: str) -> None:
        super().__init__(app)
        self._service = service_name

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        if request.url.path in ("/metrics", "/health/live", "/health/ready"):
            return await call_next(request)

        template = route_template(request)
        started = time.perf_counter()
        http_requests_in_flight.labels(self._service).inc()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            return response
        finally:
            elapsed = time.perf_counter() - started
            http_requests_in_flight.labels(self._service).dec()
            http_requests_total.labels(
                self._service, request.method, template, str(status)
            ).inc()
            http_request_duration_seconds.labels(
                self._service, request.method, template
            ).observe(elapsed)
            log.info(
                "request handled",
                extra={
                    "service": self._service,
                    "method": request.method,
                    "path": request.url.path,
                    "route": template,
                    "status": status,
                    "duration_ms": round(elapsed * 1000, 2),
                    "client": request.client.host if request.client else None,
                },
            )

class BodySizeLimitMiddleware(BaseHTTPMiddleware):

    def __init__(self, app, max_bytes: int) -> None:
        super().__init__(app)
        self._max_bytes = max_bytes

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        content_length = request.headers.get("content-length")
        if content_length and content_length.isdigit():
            if int(content_length) > self._max_bytes:
                return JSONResponse(
                    status_code=413,
                    content={
                        "error": {
                            "code": "payload_too_large",
                            "message": (
                                f"Request body exceeds {self._max_bytes} bytes."
                            ),
                            "request_id": context.get_request_id(),
                        }
                    },
                )
        return await call_next(request)
