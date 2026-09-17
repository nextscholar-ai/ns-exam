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

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.db.session import get_db
from app.core.exceptions import UnauthorizedError
from app.core.security.rbac import require_role
from app.modules.integration.erp_client import academic_cache, invalidate_academic_cache
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

router = APIRouter(
    prefix="/integration",
    tags=["integration"],
)


async def require_integration_auth(
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    x_webhook_token: str | None = Header(default=None, alias="X-Webhook-Token"),
):
    """Authenticate via API Key, Webhook Token, or User JWT Role."""
    if x_api_key and x_api_key.strip() == settings.erp.api_key.strip():
        return True
    if x_webhook_token and x_webhook_token.strip() == settings.erp.webhook_token.strip():
        return True
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()
        if token in (settings.erp.api_key, settings.erp.webhook_token):
            return True
        checker = require_role("SUPER_ADMIN", "ADMIN", "SCHOOL_ADMIN")
        return await checker(authorization=authorization)
    # Default allow for local test endpoints or require role
    checker = require_role("SUPER_ADMIN", "ADMIN", "SCHOOL_ADMIN")
    return await checker(authorization=authorization)


@router.get("/ping")
async def ping() -> dict[str, str]:
    return {"module": "integration", "status": "ok"}


@router.post(
    "/sync/academic",
    summary="Exam -> ERP round trip academic sync",
)
async def sync_academic_roundtrip(
    db: AsyncSession = Depends(get_db),
):
    """Direct endpoint to trigger full inbound sync from ERP and return 200."""
    svc = SyncService(db)
    results = await svc.sync_all(mode="FULL")
    return {"status": "success", "results": results}


@router.post(
    "/internal/cache/invalidate",
    summary="Invalidate academic cache from ERP webhook",
)
async def invalidate_academic_cache_endpoint(
    entity: str | None = Query(default=None),
    school_id: str | None = Query(default=None),
    token: str | None = Header(default=None),
    x_webhook_token: str | None = Header(default=None, alias="X-Webhook-Token"),
    authorization: str | None = Header(default=None),
):
    """Endpoint for ERP to instantly invalidate cached academic snapshot data."""
    check_token = token or x_webhook_token
    if not check_token and authorization and authorization.startswith("Bearer "):
        check_token = authorization.split(" ", 1)[1].strip()

    expected = settings.erp.webhook_token
    if expected and check_token and check_token != expected:
        raise HTTPException(status_code=403, detail="Invalid token")

    removed = invalidate_academic_cache(entity, school_id)
    return {"status": "invalidated", "entity": entity, "school_id": school_id, "removed_keys": removed}


@router.get(
    "/sync-logs",
    response_model=list[SyncLogResponse],
    dependencies=[Depends(require_integration_auth)],
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
    dependencies=[Depends(require_integration_auth)],
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
    dependencies=[Depends(require_integration_auth)],
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
    dependencies=[Depends(require_integration_auth)],
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
    dependencies=[Depends(require_integration_auth)],
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
