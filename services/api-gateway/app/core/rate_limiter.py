"""
Rate limiter: fixed-window counter in Redis.

WHY fixed-window (not sliding-window/token-bucket) for this module: it's a
single INCR + EXPIRE per request — O(1), two Redis round-trips, easy to
reason about and correct under concurrent requests (INCR is atomic). A
sliding-window log is more precise at window boundaries but costs a sorted-
set write per request; that precision isn't worth the extra Redis load at
this stage. If abuse patterns exploiting the fixed-window edge (bursting
right at the window boundary) become a real problem operationally, this is
a contained, swappable component — nothing else in the gateway depends on
which algorithm is used.

Keying: by authenticated user id when a valid token is present, otherwise
by client IP — this means a logged-in user gets a personal budget instead
of a whole NAT'd office sharing one IP's limit, while still protecting
anonymous endpoints (login, register) from being hammered.
"""

from dataclasses import dataclass

import redis.asyncio as redis


@dataclass
class RateLimitResult:
    allowed: bool
    remaining: int
    retry_after_seconds: int


class RateLimiter:
    def __init__(self, redis_client: redis.Redis, *, max_requests: int, window_seconds: int):
        self._redis = redis_client
        self._max_requests = max_requests
        self._window_seconds = window_seconds

    async def check(self, key: str) -> RateLimitResult:
        redis_key = f"ratelimit:{key}"
        # Pipeline INCR + EXPIRE atomically-enough for our purposes: EXPIRE
        # is only set on the FIRST increment of a window (NX), so a burst
        # of concurrent first-requests doesn't keep resetting the window.
        current = await self._redis.incr(redis_key)
        if current == 1:
            await self._redis.expire(redis_key, self._window_seconds)

        if current > self._max_requests:
            ttl = await self._redis.ttl(redis_key)
            return RateLimitResult(allowed=False, remaining=0, retry_after_seconds=max(ttl, 1))

        return RateLimitResult(allowed=True, remaining=self._max_requests - current, retry_after_seconds=0)
