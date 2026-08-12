"""
Idempotency-key store (Phase 7 §5.6) — for write-heavy AI/generation
endpoints like `POST /papers/generate`.

Service layer calls `idempotency_store.check_and_reserve(key)` BEFORE
triggering the expensive operation. If it returns `False`, the key was
already used within its TTL and the service should return the previously
recorded result instead of re-triggering generation.

v1 fallback: in-memory with TTL (documented, single-process only). Swap for
Redis (`SETNX` + TTL) in production without changing the call site - the
interface (`check_and_reserve`, `store_result`, `get_result`) stays the same.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any

DEFAULT_TTL_SECONDS = 24 * 60 * 60  # 24h - long enough to cover client retry storms


@dataclass
class _Entry:
    result: Any
    expires_at: float


class IdempotencyStore:
    def __init__(self, *, ttl_seconds: int = DEFAULT_TTL_SECONDS) -> None:
        self.ttl_seconds = ttl_seconds
        self._entries: dict[str, _Entry] = {}
        self._lock = threading.Lock()

    def check_and_reserve(self, key: str) -> bool:
        """Returns True if this is the first time `key` is seen (caller should
        proceed), False if it was already reserved/used (caller should look up
        the stored result instead)."""
        now = time.monotonic()
        with self._lock:
            self._evict_expired(now)
            if key in self._entries:
                return False
            self._entries[key] = _Entry(result=None, expires_at=now + self.ttl_seconds)
            return True

    def store_result(self, key: str, result: Any) -> None:
        with self._lock:
            if key in self._entries:
                self._entries[key].result = result

    def get_result(self, key: str) -> Any | None:
        with self._lock:
            entry = self._entries.get(key)
            return entry.result if entry else None

    def _evict_expired(self, now: float) -> None:
        expired = [k for k, v in self._entries.items() if v.expires_at < now]
        for k in expired:
            del self._entries[k]


idempotency_store = IdempotencyStore()
