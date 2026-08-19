"""
ERP / SIS Integration module — Router (Phase 16 §7, Phase 18 §3).

Endpoints:
  GET  /integration/ping            — health check (Phase 1 placeholder preserved).
  GET  /integration/sync-logs       — list recent ERP outbound sync audit log entries.
  POST /integration/sync-report     — manually trigger/re-trigger ERP report sync.
  POST /integration/sync/trigger    — trigger inbound academic snapshot sync (Phase 16 §7).
  GET  /integration/sync/status     — last inbound sync per entity type (Phase 16 §7).
  GET  /integration/sync/logs       — inbound sync audit log (Phase 16 §7).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.session import get_db
from app.modules.integration.schemas import (
    InboundSyncLogEntry,
    InboundSyncResult,
    InboundSyncStatus,
    InboundSyncTriggerRequest,
    SyncLogResponse,
    SyncTriggerRequest,
    SyncTriggerResponse,
)
from app.modules.integration.service import ERPIntegrationService
from app.modules.integration.sync_service import SyncService

router = APIRouter(prefix="/integration", tags=["integration"])


@router.get("/ping")
async def ping() -> dict[str, str]:
    return {"module": "integration", "status": "ok"}


@router.get(
    "/sync-logs",
    response_model=list[SyncLogResponse],
    summary="List recent ERP outbound sync audit log entries",
)
async def list_sync_logs(
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
) -> list[SyncLogResponse]:
    svc = ERPIntegrationService(db)
    logs = await svc.get_sync_logs(limit=limit)
    return [SyncLogResponse(**entry) for entry in logs]


@router.post(
    "/sync-report",
    response_model=SyncTriggerResponse,
    summary="Manually trigger or re-trigger ERP sync for a report",
)
async def sync_report(
    body: SyncTriggerRequest,
    db: AsyncSession = Depends(get_db),
) -> SyncTriggerResponse:
    svc = ERPIntegrationService(db)
    result = await svc.resync_report(body.report_public_id)
    return SyncTriggerResponse(
        log_id=result["log_id"],
        status=result["status"],
        response_code=result["response_code"],
    )


@router.post(
    "/sync/trigger",
    response_model=InboundSyncResult | list[InboundSyncResult],
    summary="Trigger inbound academic snapshot sync from the ERP",
)
async def trigger_inbound_sync(
    body: InboundSyncTriggerRequest,
    db: AsyncSession = Depends(get_db),
):
    svc = SyncService(db)
    if body.entity_type:
        result = await svc.sync_entity_type(body.entity_type, mode=body.mode)
        return InboundSyncResult(**result)
    results = await svc.sync_all(mode=body.mode)
    return [InboundSyncResult(**r) for r in results]


@router.get(
    "/sync/status",
    response_model=InboundSyncStatus,
    summary="Last inbound sync status per entity type",
)
async def inbound_sync_status(
    db: AsyncSession = Depends(get_db),
) -> InboundSyncStatus:
    svc = SyncService(db)
    return InboundSyncStatus(**await svc.get_sync_status())


@router.get(
    "/sync/logs",
    response_model=list[InboundSyncLogEntry],
    summary="Inbound sync audit log entries",
)
async def inbound_sync_logs(
    entity_type: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> list[InboundSyncLogEntry]:
    svc = SyncService(db)
    logs = await svc.get_sync_logs(entity_type=entity_type, limit=limit)
    return [InboundSyncLogEntry(**entry) for entry in logs]
