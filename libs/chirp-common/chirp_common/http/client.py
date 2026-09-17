"""Typed HTTP client for service-to-service calls.

Synchronous calls between services are where a distributed system usually
fails, so every call made through this client gets: a hard timeout, bounded
retries with jittered backoff on retry-safe methods only, a circuit breaker so
a dead dependency fails fast instead of consuming the caller's workers, and
propagation of the correlation id so one user action is traceable end to end.
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
from typing import Any, Literal

import httpx

from chirp_common import context
from chirp_common.errors import AppError, DependencyError
from chirp_common.metrics import dependency_requests_total

log = logging.getLogger(__name__)

RETRY_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "DELETE"})
RETRYABLE_STATUS = frozenset({502, 503, 504})


class CircuitBreaker:
    """Minimal breaker: open after N consecutive failures, half-open after T."""

    def __init__(self, *, failure_threshold: int = 5, reset_after_seconds: float = 10.0) -> None:
        self._threshold = failure_threshold
        self._reset_after = reset_after_seconds
        self._failures = 0
        self._opened_at: float | None = None

    @property
    def state(self) -> Literal["closed", "open", "half_open"]:
        if self._opened_at is None:
            return "closed"
        if time.monotonic() - self._opened_at >= self._reset_after:
            return "half_open"
        return "open"

    def allows(self) -> bool:
        return self.state != "open"

    def record_success(self) -> None:
        self._failures = 0
        self._opened_at = None

    def record_failure(self) -> None:
        self._failures += 1
        if self._failures >= self._threshold:
            self._opened_at = time.monotonic()


class ServiceClient:
    def __init__(
        self,
        *,
        base_url: str,
        dependency: str,
        service_name: str,
        timeout_seconds: float = 3.0,
        connect_timeout_seconds: float = 1.0,
        max_retries: int = 2,
    ) -> None:
        self._dependency = dependency
        self._service = service_name
        self._max_retries = max_retries
        self._breaker = CircuitBreaker()
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=httpx.Timeout(timeout_seconds, connect=connect_timeout_seconds),
            limits=httpx.Limits(max_connections=64, max_keepalive_connections=16),
            headers={"user-agent": f"chirp/{service_name}"},
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def ping(self) -> bool:
        try:
            response = await self._client.get("/health/live", timeout=1.0)
            return response.status_code == 200
        except httpx.HTTPError:
            return False

    async def request(
        self,
        method: str,
        path: str,
        *,
        json: Any | None = None,
        params: dict[str, Any] | None = None,
        bearer_token: str | None = None,
        retry: bool | None = None,
    ) -> Any:
        if not self._breaker.allows():
            dependency_requests_total.labels(self._service, self._dependency, "circuit_open").inc()
            raise DependencyError(
                f"{self._dependency} is unavailable (circuit open).",
                details={"dependency": self._dependency},
            )

        should_retry = method.upper() in RETRY_SAFE_METHODS if retry is None else retry
        attempts = self._max_retries + 1 if should_retry else 1
        headers = self._headers(bearer_token)
        last_error: Exception | None = None

        for attempt in range(attempts):
            try:
                response = await self._client.request(
                    method, path, json=json, params=params, headers=headers
                )
            except httpx.HTTPError as exc:
                last_error = exc
                self._breaker.record_failure()
                dependency_requests_total.labels(
                    self._service, self._dependency, "transport_error"
                ).inc()
                if attempt + 1 < attempts:
                    await self._backoff(attempt)
                    continue
                raise DependencyError(
                    f"{self._dependency} did not respond.",
                    details={"dependency": self._dependency},
                ) from exc

            if response.status_code in RETRYABLE_STATUS and attempt + 1 < attempts:
                self._breaker.record_failure()
                await self._backoff(attempt)
                continue

            return self._handle(response)

        raise DependencyError(  # pragma: no cover - loop always returns or raises
            f"{self._dependency} did not respond.",
        ) from last_error

    async def get(self, path: str, **kwargs: Any) -> Any:
        return await self.request("GET", path, **kwargs)

    async def post(self, path: str, **kwargs: Any) -> Any:
        return await self.request("POST", path, **kwargs)

    def _headers(self, bearer_token: str | None) -> dict[str, str]:
        headers = {
            context.REQUEST_ID_HEADER: context.new_id(),
            context.CORRELATION_ID_HEADER: context.get_correlation_id() or context.new_id(),
        }
        if actor := context.get_actor_id():
            headers[context.ACTOR_ID_HEADER] = actor
        if bearer_token:
            headers["authorization"] = f"Bearer {bearer_token}"
        return headers

    def _handle(self, response: httpx.Response) -> Any:
        if response.is_success:
            self._breaker.record_success()
            dependency_requests_total.labels(self._service, self._dependency, "ok").inc()
            if response.status_code == 204 or not response.content:
                return None
            return response.json()

        dependency_requests_total.labels(
            self._service, self._dependency, str(response.status_code)
        ).inc()

        if response.status_code >= 500:
            self._breaker.record_failure()
            raise DependencyError(
                f"{self._dependency} returned {response.status_code}.",
                details={"dependency": self._dependency},
            )

        # 4xx from a dependency is a real answer, not a failure: pass the
        # upstream error through so the client sees "user not found" rather
        # than "dependency unavailable".
        self._breaker.record_success()
        payload = self._safe_json(response)
        error = (payload or {}).get("error", {})
        raise AppError(
            error.get("message") or f"{self._dependency} rejected the request.",
            code=error.get("code") or "dependency_rejected",
            status_code=response.status_code,
            details=error.get("details") or {},
        )

    @staticmethod
    def _safe_json(response: httpx.Response) -> dict[str, Any] | None:
        try:
            data = response.json()
        except ValueError:
            return None
        return data if isinstance(data, dict) else None

    async def _backoff(self, attempt: int) -> None:
        # Exponential with full jitter: without jitter every caller retries in
        # lockstep and hammers a recovering dependency.
        delay = min(0.1 * (2**attempt), 2.0)
        await asyncio.sleep(random.uniform(0, delay))
