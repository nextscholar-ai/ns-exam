"""
ERP / SIS Integration module — Inbound ERP REST client (Phase 16 §5.2, §16).

`ERPClient` is the base HTTP client used to *pull* academic/student/teacher
snapshot data from the ERP (same base config as Phase 6's token-validation
call and Phase 18's outbound `WebhookClient` — see `get_erp_client()`).

Contract (Phase 16 §5.2):
  GET {ERP_BASE}/integration/academic/{boards|schools|sessions|classes|subjects|
      chapters|units|topics|students|teachers}?updated_since=&page=&page_size=
Each returns `{items: [...], page, page_size, total}` where every item carries
`erp_id`, business fields, `updated_at`, and `is_deleted`.

Phase 4: Uses shared HTTP client with connection pooling for better performance.
"""
from __future__ import annotations

from typing import Any
import time

try:
    from cachetools import TTLCache
except ImportError:
    class TTLCache(dict):
        def __init__(self, maxsize: int = 1000, ttl: int = 600) -> None:
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

from app.core.config import settings
from app.core.http import get_http_client
from app.core.logging import get_logger

logger = get_logger(__name__)

# In-memory TTL cache for ERP academic snapshots (10 min TTL, up to 1000 items)
academic_cache = TTLCache(maxsize=1000, ttl=600)


def invalidate_academic_cache(entity_type: str | None = None, school_id: str | None = None) -> int:
    """Invalidate all or entity-specific academic cache entries."""
    if entity_type is None and school_id is None:
        count = len(academic_cache)
        academic_cache.clear()
        logger.info("erp.client.cache.cleared_all", count=count)
        return count

    keys_to_remove = []
    for k in list(academic_cache.keys()):
        key_str = str(k)
        if entity_type and key_str.startswith(f"{entity_type}:"):
            keys_to_remove.append(k)
        elif school_id and f":{school_id}:" in key_str:
            keys_to_remove.append(k)

    for k in keys_to_remove:
        academic_cache.pop(k, None)

    logger.info("erp.client.cache.invalidated", entity_type=entity_type, removed=len(keys_to_remove))
    return len(keys_to_remove)


# ERP academic snapshot endpoints (see merged ERP router: /integration/academic/*)
_ACADEMIC_PREFIX = "/integration/academic"
_ENTITY_PATHS = {
    "board": "boards",
    "school": "schools",
    "session": "sessions",
    "class": "classes",
    "subject": "subjects",
    "chapter": "chapters",
    "unit": "units",
    "topic": "topics",
    "student": "students",
    "teacher": "teachers",
}


class ERPClient:
    """Async HTTP client for pulling academic snapshots from the ERP with TTL caching."""

    def __init__(
        self,
        base_url: str = "",
        api_key: str = "",
        timeout_sec: int = 10,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout_sec = timeout_sec

    async def get_academic_page(
        self,
        entity_type: str,
        *,
        updated_since: str | None = None,
        page: int = 1,
        page_size: int = 100,
        bypass_cache: bool = False,
    ) -> dict[str, Any]:
        """Fetch one page of an academic snapshot entity from the ERP with TTL caching.

        Returns the raw ERP payload dict (`{items, page, page_size, total}`).
        Raises nothing on HTTP errors — returns an empty page envelope so the
        caller can log the failure and keep the sync audit trail accurate.
        """
        path = _ENTITY_PATHS.get(entity_type)
        if path is None:
            logger.error("erp.client.unknown_entity", entity_type=entity_type)
            return {"items": [], "page": page, "page_size": page_size, "total": 0}

        cache_key = f"{entity_type}:{page}:{page_size}"
        if not bypass_cache and not updated_since and cache_key in academic_cache:
            logger.info("erp.client.cache.hit", entity_type=entity_type, page=page)
            return academic_cache[cache_key]

        url = f"{self.base_url}{_ACADEMIC_PREFIX}/{path}"
        params: dict[str, Any] = {"page": page, "page_size": page_size}
        if updated_since:
            params["updated_since"] = updated_since

        headers = {"Accept": "application/json"}
        if self.api_key:
            headers["X-API-Key"] = self.api_key

        logger.info(
            "erp.client.pull.sending",
            url=url,
            entity_type=entity_type,
            page=page,
        )

        try:
            client = get_http_client()
            response = await client.get(url, params=params, headers=headers)
            if response.status_code >= 400:
                logger.warning(
                    "erp.client.pull.http_error",
                    entity_type=entity_type,
                    status_code=response.status_code,
                )
                return {"items": [], "page": page, "page_size": page_size, "total": 0}
            data = response.json()
        except Exception as exc:
            logger.error("erp.client.pull.network_error", entity_type=entity_type, error=str(exc))
            return {"items": [], "page": page, "page_size": page_size, "total": 0}

        if not updated_since and data.get("items"):
            academic_cache[cache_key] = data

        logger.info(
            "erp.client.pull.done",
            entity_type=entity_type,
            page=page,
            items=len(data.get("items", [])),
        )
        return data

    @property
    def is_configured(self) -> bool:
        return bool(self.base_url)


def get_erp_client() -> ERPClient:
    """Factory — reads from `settings.erp`. Used by `SyncService` default arg."""
    return ERPClient(
        base_url=settings.erp.base_url,
        api_key=settings.erp.api_key,
        timeout_sec=settings.erp.webhook_timeout_sec,
    )


async def get_classes_for_school(school_id: str = "SCH-001") -> dict[str, Any]:
    """Helper to fetch cached classes for a school."""
    client = get_erp_client()
    return await client.get_academic_page("class")
