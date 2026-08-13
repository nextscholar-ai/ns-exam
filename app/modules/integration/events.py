"""
ERP / SIS Integration module — Domain Events (Phase 18 §3).

Publishes `ERPSynced` event and registers cross-module event handlers that
call the ERP integration service when reports are generated or students are
flagged at-risk.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from app.core.db.session import db_session_scope
from app.core.events.bus import event_bus
from app.core.events.event_names import (
    ANALYTICS_UPDATED,
    ERP_SYNCED,
    REPORT_GENERATED,
)
from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class ERPSynced:
    log_id: str
    event_name: str
    status: str
    response_code: int


async def publish_erp_synced(event: ERPSynced) -> None:
    await event_bus.publish(ERP_SYNCED, asdict(event))


# ---------------------------------------------------------------------------
# Cross-module event handlers
# ---------------------------------------------------------------------------

async def _on_report_generated_for_erp(payload: dict[str, Any]) -> None:
    """Sync report generation event to ERP when a report is produced."""
    report_public_id = payload.get("report_public_id")
    if not report_public_id:
        return

    async with db_session_scope() as session:
        from app.modules.integration.service import ERPIntegrationService
        svc = ERPIntegrationService(session)
        result = await svc.sync_report(
            report_public_id=report_public_id,
            student_id=payload.get("student_id"),
            exam_id=payload.get("exam_id"),
            report_type=payload.get("report_type", "UNKNOWN"),
        )
        logger.info(
            "integration.handler.report_generated",
            report_public_id=report_public_id,
            sync_status=result.get("status"),
        )


async def _on_analytics_updated_for_erp(payload: dict[str, Any]) -> None:
    """Sync at-risk flag to ERP when student analytics are updated."""
    student_id = payload.get("student_id")
    is_at_risk = payload.get("is_at_risk", False)

    # Only sync when there is a meaningful update (at-risk flag change)
    if not student_id:
        return

    async with db_session_scope() as session:
        from app.modules.integration.service import ERPIntegrationService
        svc = ERPIntegrationService(session)
        result = await svc.sync_analytics_at_risk(
            student_id=student_id,
            is_at_risk=is_at_risk,
            class_id=payload.get("class_id"),
        )
        logger.info(
            "integration.handler.analytics_updated",
            student_id=student_id,
            is_at_risk=is_at_risk,
            sync_status=result.get("status"),
        )


def register_integration_event_handlers() -> None:
    """
    Subscribe integration handlers to the EventBus.

    Called once from `app.main` lifespan on startup, after
    `register_all_handlers()`.
    """
    event_bus.subscribe(REPORT_GENERATED, _on_report_generated_for_erp)
    event_bus.subscribe(ANALYTICS_UPDATED, _on_analytics_updated_for_erp)
    logger.info("event_bus.integration_handlers_registered", count=2)
