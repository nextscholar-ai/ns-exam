"""
Token-bucket rate limiter (Phase 7 §5.8).

v1 implementation is per-process in-memory - correct for a single instance,
an approximation once horizontally scaled. Swap for a Redis-backed bucket at
that point; the `allow(key, strict)` interface doesn't need to change.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass


@dataclass
class _Bucket:
    tokens: float
    last_refill: float


class RateLimiter:
    def __init__(
        self,
        *,
        default_capacity: int = 120,
        default_refill_per_second: float = 2.0,
        strict_capacity: int = 10,
        strict_refill_per_second: float = 0.2,
    ) -> None:
        """
        Defaults: 120 requests/min general, 10 requests/min on strict
        (`/auth/*` and, later, `/papers/generate`) paths (Phase 7 §5.8).
        """
        self.default_capacity = default_capacity
        self.default_refill_per_second = default_refill_per_second
        self.strict_capacity = strict_capacity
        self.strict_refill_per_second = strict_refill_per_second
        self._buckets: dict[str, _Bucket] = {}
        self._lock = threading.Lock()

    def allow(self, key: str, *, strict: bool = False) -> bool:
        capacity = self.strict_capacity if strict else self.default_capacity
        refill_rate = self.strict_refill_per_second if strict else self.default_refill_per_second
        bucket_key = f"{'strict' if strict else 'default'}:{key}"

        now = time.monotonic()
        with self._lock:
            bucket = self._buckets.get(bucket_key)
            if bucket is None:
                bucket = _Bucket(tokens=capacity - 1, last_refill=now)
                self._buckets[bucket_key] = bucket
                return True

            elapsed = now - bucket.last_refill
            bucket.tokens = min(capacity, bucket.tokens + elapsed * refill_rate)
            bucket.last_refill = now

            if bucket.tokens >= 0.99:
                bucket.tokens -= 1.0
                return True
            return False

    def reset(self) -> None:
        """Test helper."""
        with self._lock:
            self._buckets.clear()


rate_limiter = RateLimiter()
