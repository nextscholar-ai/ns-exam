"""
ERP / SIS Integration module — Pydantic schemas (Phase 18 §3).
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
