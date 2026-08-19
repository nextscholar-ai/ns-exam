"""
ERP / SIS Integration module — ORM models (Phase 16 §5.6, Phase 18 §3).

Tables owned here:
  sync_logs     — outbound ERP webhook sync audit log (append-only, Phase 18).
  erp_sync_logs — inbound academic snapshot sync audit log (Phase 16 §5.6).
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db.base_model import Base, BaseMixin


class SyncLog(BaseMixin, Base):
    """
    Audit record for each outbound ERP webhook sync attempt (Phase 18 §3).

    Phase 3 §9: append-only log table — is_deleted/deleted_at/deleted_by
    columns are inherited from BaseMixin but should never be set.
    """

    __tablename__ = "sync_logs"
    __table_args__ = (
        Index("ix_sl_event_name", "event_name"),
        Index("ix_sl_status", "status"),
        Index("ix_sl_payload_hash", "payload_hash"),
    )

    event_name: Mapped[str] = mapped_column(String(64), nullable=False)
    # SHA-256 hex of canonical payload JSON — used for idempotency / dedup
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="PENDING"
    )  # PENDING | SENT | FAILED
    response_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    synced_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class ErpSyncLog(BaseMixin, Base):
    """
    Inbound academic snapshot sync audit record (Phase 16 §5.6).

    One row per sync run (per entity type). Tracks what was pulled from the
    ERP and whether the run succeeded / partially failed. Read by the
    `GET /integration/sync/status` and `GET /integration/sync/logs` endpoints.
    """

    __tablename__ = "erp_sync_logs"
    __table_args__ = (
        Index("ix_esl_sync_type", "sync_type"),
        Index("ix_esl_entity_type", "entity_type"),
        Index("ix_esl_status", "status"),
    )

    sync_type: Mapped[str] = mapped_column(String(20), nullable=False)  # FULL | INCREMENTAL | MANUAL
    entity_type: Mapped[str] = mapped_column(String(30), nullable=False)  # board/school/.../student
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    records_pulled: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    records_updated: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    records_failed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="SUCCESS"
    )  # SUCCESS | PARTIAL | FAILED
    error_detail: Mapped[str | None] = mapped_column(Text, nullable=True)


def compute_payload_hash(payload: dict[str, Any]) -> str:
    """SHA-256 of canonical (sorted-key) JSON — stable across dict ordering."""
    canonical = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()
