"""
ERP / SIS Integration module — Router (Phase 18 §3).

Endpoints:
  GET  /integration/ping            — health check (Phase 1 placeholder preserved).
  GET  /integration/sync-logs       — list recent ERP sync audit log entries.
  POST /integration/sync-report     — manually trigger/re-trigger ERP report sync.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.session import get_db
from app.modules.integration.schemas import (
    SyncLogResponse,
    SyncTriggerRequest,
    SyncTriggerResponse,
)
from app.modules.integration.service import ERPIntegrationService

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
