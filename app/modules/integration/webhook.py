"""
ERP / SIS Webhook Client (Phase 18 §3).

Provides:
  - `WebhookClient`: real async HTTP client using `httpx`.
  - `MockWebhookClient`: in-process test double, records all calls.

Architecture contract:
  - Caller passes a pre-built payload dict; client handles auth/headers.
  - Client is stateless — a new `httpx.AsyncClient` per call (simplest for
    Phase 18; Phase 19 can swap to connection pooling).
  - `base_url` defaults to `settings.erp.base_url`; can be overridden in tests.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class WebhookResponse:
    status_code: int
    body: str
    ok: bool  # True if 2xx
    sent_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class WebhookClient:
    """
    Async HTTP webhook client for ERP outbound sync calls.

    Raises nothing on HTTP errors — returns a `WebhookResponse` with ok=False
    so the caller (`ERPIntegrationService`) can decide how to log/retry.
    """

    def __init__(
        self,
        base_url: str = "",
        token: str = "",
        timeout_sec: int = 10,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout_sec = timeout_sec

    async def post(self, path: str, payload: dict[str, Any]) -> WebhookResponse:
        """POST payload to `{base_url}/{path}` with bearer token auth."""
        import httpx

        url = f"{self.base_url}/{path.lstrip('/')}"
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        logger.info(
            "webhook.post.sending",
            url=url,
            payload_keys=list(payload.keys()),
        )

        try:
            async with httpx.AsyncClient(timeout=self.timeout_sec) as client:
                response = await client.post(url, json=payload, headers=headers)
            result = WebhookResponse(
                status_code=response.status_code,
                body=response.text[:500],  # cap logged body size
                ok=response.is_success,
            )
        except Exception as exc:
            logger.error("webhook.post.network_error", url=url, error=str(exc))
            result = WebhookResponse(status_code=0, body=str(exc), ok=False)

        logger.info(
            "webhook.post.done",
            url=url,
            status_code=result.status_code,
            ok=result.ok,
        )
        return result


class MockWebhookClient:
    """
    In-process test double — records calls instead of making HTTP requests.

    Usage in tests:
        mock = MockWebhookClient()
        svc = ERPIntegrationService(session, webhook_client=mock)
        await svc.sync_report(...)
        assert len(mock.calls) == 1
    """

    def __init__(self, default_status: int = 200) -> None:
        self.default_status = default_status
        self.calls: list[dict[str, Any]] = []

    async def post(self, path: str, payload: dict[str, Any]) -> WebhookResponse:
        self.calls.append({"path": path, "payload": payload})
        ok = 200 <= self.default_status < 300
        return WebhookResponse(
            status_code=self.default_status,
            body="{}",
            ok=ok,
        )


def get_webhook_client() -> WebhookClient:
    """Factory — reads from `settings.erp`. Used by `ERPIntegrationService` default arg."""
    from app.core.config import settings

    return WebhookClient(
        base_url=settings.erp.base_url,
        token=settings.erp.webhook_token,
        timeout_sec=settings.erp.webhook_timeout_sec,
    )
