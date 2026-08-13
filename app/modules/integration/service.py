"""
ERP / SIS Integration module — Service layer (Phase 18 §3).

`ERPIntegrationService` handles:
  - Outbound sync of report generation events to ERP.
  - Outbound sync of at-risk student flags to ERP.
  - Idempotency: skips re-sending if the same payload was already SENT.
  - Audit logging via `SyncLogRepository`.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.modules.integration.models import compute_payload_hash
from app.modules.integration.repository import SyncLogRepository
from app.modules.integration.webhook import WebhookClient, get_webhook_client

logger = get_logger(__name__)

# ERP webhook endpoint paths
_PATH_REPORT = "/webhooks/report-generated"
_PATH_AT_RISK = "/webhooks/student-at-risk"


class ERPIntegrationService:
    def __init__(
        self,
        session: AsyncSession,
        webhook_client: WebhookClient | None = None,
    ) -> None:
        self.session = session
        self.repo = SyncLogRepository(session)
        # Allow injection of MockWebhookClient in tests
        self.client: WebhookClient = webhook_client or get_webhook_client()

    # ------------------------------------------------------------------
    # Outbound sync — Report Generated
    # ------------------------------------------------------------------

    async def sync_report(
        self,
        report_public_id: str,
        student_id: int | None,
        exam_id: int | None,
        report_type: str,
    ) -> dict[str, Any]:
        """
        Sync a report-generated event to the ERP.

        Idempotency: if the same payload was already SENT, skip and return
        the existing result so re-triggers are safe.
        """
        payload: dict[str, Any] = {
            "event": "report_generated",
            "report_public_id": report_public_id,
            "student_id": student_id,
            "exam_id": exam_id,
            "report_type": report_type,
        }
        return await self._sync(event_name="ReportGenerated", path=_PATH_REPORT, payload=payload)

    # ------------------------------------------------------------------
    # Outbound sync — At-Risk Student Flag
    # ------------------------------------------------------------------

    async def sync_analytics_at_risk(
        self,
        student_id: int,
        is_at_risk: bool,
        class_id: int | None = None,
    ) -> dict[str, Any]:
        """Sync an at-risk flag update to the ERP/SIS."""
        payload: dict[str, Any] = {
            "event": "student_at_risk",
            "student_id": student_id,
            "is_at_risk": is_at_risk,
            "class_id": class_id,
        }
        return await self._sync(event_name="AnalyticsUpdated", path=_PATH_AT_RISK, payload=payload)

    # ------------------------------------------------------------------
    # Manual re-sync (called from router)
    # ------------------------------------------------------------------

    async def resync_report(self, report_public_id: str) -> dict[str, Any]:
        """Force a re-sync for a specific report (bypasses dedup check)."""
        payload: dict[str, Any] = {
            "event": "report_generated",
            "report_public_id": report_public_id,
            "forced_resync": True,
        }
        log = await self.repo.create("ReportGenerated", payload)
        response = await self.client.post(_PATH_REPORT, payload)
        if response.ok:
            await self.repo.mark_sent(log.id, response.status_code, response.body)
        else:
            await self.repo.mark_failed(log.id, response.status_code, response.body)
        return {
            "log_id": str(log.public_id),
            "status": "SENT" if response.ok else "FAILED",
            "response_code": response.status_code,
        }

    # ------------------------------------------------------------------
    # Audit log queries
    # ------------------------------------------------------------------

    async def get_sync_logs(self, limit: int = 50) -> list[dict[str, Any]]:
        """Return the most recent sync log entries."""
        logs = await self.repo.list_recent(limit=limit)
        return [
            {
                "id": str(log.public_id),
                "event_name": log.event_name,
                "status": log.status,
                "response_code": log.response_code,
                "synced_at": log.synced_at.isoformat() if log.synced_at else None,
                "created_at": log.created_at.isoformat(),
            }
            for log in logs
        ]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _sync(
        self,
        event_name: str,
        path: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Core sync pipeline:
          1. Compute payload hash.
          2. Check for existing SENT log with same hash → skip if found.
          3. Create PENDING log.
          4. POST to ERP webhook.
          5. Mark SENT or FAILED.
        """
        payload_hash = compute_payload_hash(payload)

        # Idempotency check
        existing = await self.repo.get_by_payload_hash(payload_hash)
        if existing and existing.status == "SENT":
            logger.info(
                "erp.sync.skipped_duplicate",
                event_name=event_name,
                payload_hash=payload_hash,
                log_id=str(existing.public_id),
            )
            return {
                "log_id": str(existing.public_id),
                "status": "SKIPPED_DUPLICATE",
                "response_code": existing.response_code,
            }

        log = await self.repo.create(event_name, payload)

        if not self.client.base_url:
            # ERP not configured — log and return without HTTP call
            logger.info(
                "erp.sync.no_erp_configured",
                event_name=event_name,
                log_id=str(log.public_id),
            )
            await self.repo.mark_failed(log.id, 0, "ERP_URL_NOT_CONFIGURED")
            return {
                "log_id": str(log.public_id),
                "status": "SKIPPED_NO_ERP",
                "response_code": 0,
            }

        response = await self.client.post(path, payload)

        if response.ok:
            await self.repo.mark_sent(log.id, response.status_code, response.body)
            status = "SENT"
        else:
            await self.repo.mark_failed(log.id, response.status_code, response.body)
            status = "FAILED"

        logger.info(
            "erp.sync.result",
            event_name=event_name,
            log_id=str(log.public_id),
            status=status,
            response_code=response.status_code,
        )
        return {
            "log_id": str(log.public_id),
            "status": status,
            "response_code": response.status_code,
        }
