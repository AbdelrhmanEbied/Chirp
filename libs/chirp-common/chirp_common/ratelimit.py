from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Protocol

import redis.asyncio as redis
from redis.exceptions import RedisError

log = logging.getLogger(__name__)

@dataclass(frozen=True, slots=True)
class RateLimitResult:
    allowed: bool
    remaining: int
    retry_after_seconds: int

@dataclass(frozen=True, slots=True)
class RateLimitPolicy:
    limit: int
    window_seconds: int

    def key(self, scope: str, identity: str) -> str:
        window = int(time.time()) // self.window_seconds
        return f"ratelimit:{scope}:{identity}:{window}"

class RateLimiter(Protocol):
    async def check(
        self, scope: str, identity: str, policy: RateLimitPolicy
    ) -> RateLimitResult: ...

class NullRateLimiter:

    async def check(
        self, scope: str, identity: str, policy: RateLimitPolicy
    ) -> RateLimitResult:
        return RateLimitResult(True, policy.limit, 0)

class RedisRateLimiter:
    def __init__(self, client: redis.Redis) -> None:
        self._client = client

    async def check(
        self, scope: str, identity: str, policy: RateLimitPolicy
    ) -> RateLimitResult:
        key = policy.key(scope, identity)
        try:
            async with self._client.pipeline(transaction=True) as pipe:
                pipe.incr(key)
                pipe.expire(key, policy.window_seconds)
                count, _ = await pipe.execute()
        except RedisError as exc:
            log.warning(
                "rate limiter unavailable, allowing request",
                extra={"scope": scope, "error": str(exc)},
            )
            return RateLimitResult(True, policy.limit, 0)

        remaining = max(0, policy.limit - int(count))
        if int(count) > policy.limit:
            elapsed = int(time.time()) % policy.window_seconds
            return RateLimitResult(False, 0, policy.window_seconds - elapsed)
        return RateLimitResult(True, remaining, 0)
