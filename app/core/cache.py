"""
In-process, short-TTL cache (Phase 8 §5.5) — for read-heavy, rarely-changing
data ONLY: the Academic Snapshot tree and RBAC `role_permissions`.
Transactional data (Questions, Papers, Exams, Evaluations) is NEVER cached
here - staleness there is a correctness bug, not a performance nuisance.

v1: `cachetools.TTLCache`, in-process, 60s default TTL. Future (Phase 21
roadmap): swap for a Redis-backed cache without changing call sites - the
cache is an implementation detail behind the repository interface, never
imported by service.py directly.
"""
from __future__ import annotations

import functools
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

try:
    from cachetools import TTLCache
except ImportError:
    import time

    class TTLCache(dict):
        def __init__(self, maxsize: int = 512, ttl: int = 60) -> None:
            super().__init__()
            self.maxsize = maxsize
            self.ttl = ttl
            self._timestamps: dict[Any, float] = {}

        def __getitem__(self, key: Any) -> Any:
            if key in self._timestamps:
                if time.time() - self._timestamps[key] > self.ttl:
                    del self[key]
                    del self._timestamps[key]
                    raise KeyError(key)
            return super().__getitem__(key)

        def __setitem__(self, key: Any, value: Any) -> None:
            if len(self) >= self.maxsize and key not in self:
                oldest = min(self._timestamps, key=lambda k: self._timestamps[k], default=None)
                if oldest is not None:
                    del self[oldest]
                    del self._timestamps[oldest]
            super().__setitem__(key, value)
            self._timestamps[key] = time.time()

        def pop(self, key: Any, default: Any = None) -> Any:
            self._timestamps.pop(key, None)
            return super().pop(key, default)

        def clear(self) -> None:
            self._timestamps.clear()
            super().clear()


DEFAULT_TTL_SECONDS = 60
DEFAULT_MAX_SIZE = 512

T = TypeVar("T")


class AsyncTTLCache:
    """Wraps `cachetools.TTLCache` for async methods. Not thread-safe across
    multiple event loops, which is fine for a single-process ASGI app."""

    def __init__(self, *, ttl_seconds: int = DEFAULT_TTL_SECONDS, maxsize: int = DEFAULT_MAX_SIZE) -> None:
        self._cache: TTLCache = TTLCache(maxsize=maxsize, ttl=ttl_seconds)

    async def get_or_set(self, key: Any, factory: Callable[[], Awaitable[T]]) -> T:
        try:
            return self._cache[key]
        except KeyError:
            pass
        value = await factory()
        self._cache[key] = value
        return value

    def invalidate(self, key: Any) -> None:
        self._cache.pop(key, None)

    def clear(self) -> None:
        self._cache.clear()


def cached_ttl(cache: AsyncTTLCache, key_fn: Callable[..., Any]):
    """
    Decorator for repository methods:
        _role_cache = AsyncTTLCache(ttl_seconds=60)

        @cached_ttl(_role_cache, key_fn=lambda self, name: f"role:{name}")
        async def get_by_name(self, name: str) -> Role | None: ...
    """

    def decorator(func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> T:
            key = key_fn(*args, **kwargs)
            return await cache.get_or_set(key, lambda: func(*args, **kwargs))

        return wrapper

    return decorator
