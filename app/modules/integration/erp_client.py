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
"""
from __future__ import annotations

from typing import Any

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

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
    """Async HTTP client for pulling academic snapshots from the ERP."""

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
    ) -> dict[str, Any]:
        """Fetch one page of an academic snapshot entity from the ERP.

        Returns the raw ERP payload dict (`{items, page, page_size, total}`).
        Raises nothing on HTTP errors — returns an empty page envelope so the
        caller can log the failure and keep the sync audit trail accurate.
        """
        import httpx

        path = _ENTITY_PATHS.get(entity_type)
        if path is None:
            logger.error("erp.client.unknown_entity", entity_type=entity_type)
            return {"items": [], "page": page, "page_size": page_size, "total": 0}

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
            async with httpx.AsyncClient(timeout=self.timeout_sec) as client:
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
