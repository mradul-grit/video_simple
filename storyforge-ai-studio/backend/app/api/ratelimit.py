"""Fixed-window rate limits for write and job-starting endpoints.

Redis is the shared store (one counter per key and window, with expiry). Tests and
single-process development can use the in-memory store (RATE_LIMIT_BACKEND=memory).
If Redis is unreachable the limiter fails open and logs a warning: an outage of the
limiter must not take the API down.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, HTTPException, Request

from app.api.deps import get_current_user
from app.config import settings
from app.db.models import User

logger = logging.getLogger(__name__)

# name -> (requests, window seconds). Per user unless noted.
LIMITS: dict[str, tuple[int, int]] = {
    "auth:dev-login": (10, 60),  # per client IP
    "projects:create": (20, 60),
    "media:upload-url": (20, 60),
    "analysis:enqueue": (10, 60),
    "visual:enqueue": (10, 60),
    "renders:enqueue": (10, 60),
    "jobs:retry": (10, 60),
}


class MemoryStore:
    def __init__(self) -> None:
        self._hits: dict[tuple[str, int], int] = {}
        self._lock = threading.Lock()

    def hit(self, key: str, window: int) -> int:
        bucket = int(time.time() // window)
        with self._lock:
            for k in [k for k in self._hits if k[1] < bucket]:
                del self._hits[k]
            self._hits[(key, bucket)] = self._hits.get((key, bucket), 0) + 1
            return self._hits[(key, bucket)]

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


class RedisStore:
    def __init__(self, url: str) -> None:
        from redis import Redis

        self._redis = Redis.from_url(url, socket_connect_timeout=0.5, socket_timeout=0.5)

    def hit(self, key: str, window: int) -> int:
        bucket = int(time.time() // window)
        rkey = f"rl:{key}:{bucket}"
        pipe = self._redis.pipeline()
        pipe.incr(rkey)
        pipe.expire(rkey, window + 5)
        count, _ = pipe.execute()
        return int(count)


_store: MemoryStore | RedisStore | None = None


def get_store() -> MemoryStore | RedisStore:
    global _store
    if _store is None:
        _store = (
            MemoryStore()
            if settings.rate_limit_backend == "memory"
            else RedisStore(settings.redis_url)
        )
    return _store


def reset_store() -> None:
    """For tests: drop counters and re-read the configured backend."""
    global _store
    _store = None


def _check(name: str, subject: str) -> None:
    if not settings.rate_limit_enabled:
        return
    limit, window = LIMITS[name]
    try:
        count = get_store().hit(f"{name}:{subject}", window)
    except Exception:  # limiter outage: fail open, never block the API
        logger.warning("rate limiter unavailable; allowing request (%s)", name)
        return
    if count > limit:
        retry_after = window - int(time.time()) % window
        raise HTTPException(
            status_code=429,
            detail=f"Too many requests. Try again in {retry_after} seconds.",
            headers={"Retry-After": str(retry_after)},
        )


def per_user(name: str) -> Callable[..., None]:
    def dependency(user: Annotated[User, Depends(get_current_user)]) -> None:
        _check(name, user.id)

    return dependency


def per_ip(name: str) -> Callable[..., None]:
    def dependency(request: Request) -> None:
        _check(name, request.client.host if request.client else "unknown")

    return dependency
