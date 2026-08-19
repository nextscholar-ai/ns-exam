"""
ERP / SIS Integration module — Pydantic schemas (Phase 16 §7, Phase 18 §3).
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class SyncLogResponse(BaseModel):
    id: str
    event_name: str
    status: str  # PENDING | SENT | FAILED
    response_code: int | None = None
    synced_at: str | None = None
    created_at: str


class SyncTriggerRequest(BaseModel):
    report_public_id: str


class SyncTriggerResponse(BaseModel):
    log_id: str
    status: str
    response_code: int


class InboundSyncTriggerRequest(BaseModel):
    entity_type: str | None = None  # board/school/... or None = all
    mode: str = "FULL"  # FULL | INCREMENTAL | MANUAL


class InboundSyncResult(BaseModel):
    entity_type: str
    mode: str
    status: str  # SUCCESS | PARTIAL | FAILED | SKIPPED_NO_ERP
    pulled: int = 0
    updated: int = 0
    failed: int = 0
    error: str | None = None


class InboundSyncLogEntry(BaseModel):
    id: str
    sync_type: str
    entity_type: str
    status: str
    records_pulled: int
    records_updated: int
    records_failed: int
    error_detail: str | None = None
    started_at: str
    completed_at: str | None = None


class InboundSyncStatus(BaseModel):
    erp_configured: bool
    erp_base_url: str
    per_entity: dict[str, Any]
