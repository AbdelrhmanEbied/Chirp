"""Cache abstraction.

Rules this codebase follows, and the reasoning is in docs/decisions.md:

* Redis is never the source of truth. Every cached value can be recomputed
  from PostgreSQL.
* A cache failure is a miss, not an error. If Redis is down the request is
  slower, not broken.
* Writes invalidate rather than update, so a failed invalidation costs one
  stale TTL window instead of permanently wrong data.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Awaitable, Callable, Protocol

import redis.asyncio as redis
from redis.exceptions import RedisError

from chirp_common.metrics import cache_operations_total

log = logging.getLogger(__name__)


class Cache(Protocol):
    async def get(self, key: str) -> Any | None: ...
    async def set(self, key: str, value: Any, ttl_seconds: int | None = None) -> None: ...
    async def delete(self, *keys: str) -> None: ...
    async def get_or_set(
        self, key: str, loader: Callable[[], Awaitable[Any]], ttl_seconds: int | None = None
    ) -> Any: ...


class NullCache:
    """Used in tests and when caching is disabled. Always a miss."""

    async def get(self, key: str) -> Any | None:
        return None

    async def set(self, key: str, value: Any, ttl_seconds: int | None = None) -> None:
        return None

    async def delete(self, *keys: str) -> None:
        return None

    async def get_or_set(
        self, key: str, loader: Callable[[], Awaitable[Any]], ttl_seconds: int | None = None
    ) -> Any:
        return await loader()


class RedisCache:
    def __init__(
        self,
        client: redis.Redis,
        *,
        service: str,
        namespace: str,
        default_ttl_seconds: int = 60,
    ) -> None:
        self._client = client
        self._service = service
        self._namespace = namespace
        self._default_ttl = default_ttl_seconds

    def _key(self, key: str) -> str:
        return f"{self._namespace}:{key}"

    def _record(self, result: str) -> None:
        cache_operations_total.labels(self._service, self._namespace, result).inc()

    async def get(self, key: str) -> Any | None:
        try:
            raw = await self._client.get(self._key(key))
        except RedisError as exc:
            self._record("error")
            log.warning("cache get failed", extra={"key": key, "error": str(exc)})
            return None
        if raw is None:
            self._record("miss")
            return None
        self._record("hit")
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            # Poisoned entry (format change, truncated write): drop and miss.
            await self.delete(key)
            return None

    async def set(self, key: str, value: Any, ttl_seconds: int | None = None) -> None:
        try:
            await self._client.set(
                self._key(key),
                json.dumps(value, separators=(",", ":"), default=str),
                ex=ttl_seconds or self._default_ttl,
            )
        except RedisError as exc:
            self._record("error")
            log.warning("cache set failed", extra={"key": key, "error": str(exc)})

    async def delete(self, *keys: str) -> None:
        if not keys:
            return
        try:
            await self._client.delete(*[self._key(k) for k in keys])
        except RedisError as exc:
            self._record("error")
            log.warning("cache delete failed", extra={"error": str(exc)})

    async def get_or_set(
        self, key: str, loader: Callable[[], Awaitable[Any]], ttl_seconds: int | None = None
    ) -> Any:
        cached = await self.get(key)
        if cached is not None:
            return cached
        value = await loader()
        if value is not None:
            await self.set(key, value, ttl_seconds)
        return value
