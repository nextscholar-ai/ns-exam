"""
ERP / SIS Integration module — Inbound SyncService (Phase 16 §5.2, §8, §16).

Pulls academic/student/teacher snapshot data from the ERP and upserts it into
the Exam Engine's Phase 4 snapshot tables. ERP is always the source of truth
(Phase 16 §5.3) — local snapshot values are always overwritten by the incoming
ERP value, never merged.

Pipeline per entity type (`sync_entity_type`):
  1. Fetch pages from ERP (`ERPClient.get_academic_page`).
  2. Upsert each record into the matching snapshot table by `erp_id`.
  3. Set `sync_status=SYNCED`, `synced_at=now()`.
  4. ERP-deleted records → local soft delete (Phase 3 §6.4).
  5. Full sync: erp_ids previously synced but absent from the response are
     flagged `sync_status=MISSING_IN_ERP` (never auto-deleted, Phase 16 §5.2).
  6. Every run is audited in `erp_sync_logs` (§5.6).
"""
from __future__ import annotations

import asyncio
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import Date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.modules.academic.models import (
    AcademicSession,
    Board,
    Chapter,
    Class,
    School,
    Subject,
    Topic,
    Unit,
)
from app.modules.integration.erp_client import ERPClient, get_erp_client
from app.modules.integration.repository import ErpSyncLogRepository

logger = get_logger(__name__)

# Entity config: ERP entity_type → (snapshot model, erp-relationship field names)
# `fks` maps an ERP payload field name to the local FK column that must be
# resolved from the just-synced snapshot tree (erp_id → local PK).


def _entity_config() -> dict[str, dict[str, Any]]:
    return {
        "board": {"model": Board, "fks": {}},
        "school": {"model": School, "fks": {"board_erp_id": "board_id"}},
        "session": {"model": AcademicSession, "fks": {"school_erp_id": "school_id"}},
        "class": {"model": Class, "fks": {"school_erp_id": "school_id"}},
        "subject": {
            "model": Subject,
            "fks": {"board_erp_id": "board_id", "class_erp_id": "class_id"},
        },
        "chapter": {"model": Chapter, "fks": {"subject_erp_id": "subject_id"}},
        "unit": {"model": Unit, "fks": {"chapter_erp_id": "chapter_id"}},
        "topic": {"model": Topic, "fks": {"unit_erp_id": "unit_id"}},
    }


class SyncService:
    """Inbound academic snapshot synchronization from the ERP."""

    def __init__(
        self,
        session: AsyncSession,
        erp_client: ERPClient | None = None,
    ) -> None:
        self.session = session
        self.client: ERPClient = erp_client or get_erp_client()
        self.log_repo = ErpSyncLogRepository(session)

    # ------------------------------------------------------------------
    # Public entry points
    # ------------------------------------------------------------------

    async def sync_entity_type(self, entity_type: str, mode: str = "FULL") -> dict[str, Any]:
        """Sync one entity type. `mode` is FULL | INCREMENTAL | MANUAL."""
        config = _entity_config().get(entity_type)
        if config is None:
            raise ValueError(f"Unknown entity type: {entity_type}")

        log = await self.log_repo.create_run(mode.upper(), entity_type)

        if not self.client.is_configured:
            await self.log_repo.finish_run(
                log.id,
                records_pulled=0,
                records_updated=0,
                records_failed=0,
                status="FAILED",
                error_detail="ERP_API_BASE_URL not configured",
            )
            return {"entity_type": entity_type, "status": "SKIPPED_NO_ERP", "pulled": 0, "updated": 0}

        model = config["model"]
        fks = config["fks"]

        pulled = 0
        updated = 0
        failed = 0
        errors: list[str] = []

        page = 1
        while True:
            payload = await self.client.get_academic_page(
                entity_type,
                page=page,
                page_size=100,
            )
            items = payload.get("items", [])
            if not items:
                break
            for item in items:
                try:
                    updated += await self._upsert_record(model, fks, item)
                except Exception as exc:  # noqa: BLE001 - keep sync alive per-record
                    failed += 1
                    errors.append(f"{item.get('erp_id')}: {exc}")
                    logger.warning(
                        "erp.sync.record_failed",
                        entity_type=entity_type,
                        erp_id=item.get("erp_id"),
                        error=str(exc),
                    )
                pulled += 1
            total = int(payload.get("total", 0))
            page_size = int(payload.get("page_size", 100))
            if page * page_size >= total:
                break
            page += 1

        if mode.upper() == "FULL":
            await self._mark_missing(model, entity_type, pulled)

        await self.session.commit()

        status = "SUCCESS" if failed == 0 else "PARTIAL"
        await self.log_repo.finish_run(
            log.id,
            records_pulled=pulled,
            records_updated=updated,
            records_failed=failed,
            status=status,
            error_detail="; ".join(errors[:5]) if errors else None,
        )
        await self.session.commit()

        logger.info(
            "erp.sync.entity_completed",
            entity_type=entity_type,
            mode=mode,
            pulled=pulled,
            updated=updated,
            failed=failed,
        )
        return {
            "entity_type": entity_type,
            "mode": mode.upper(),
            "status": status,
            "pulled": pulled,
            "updated": updated,
            "failed": failed,
        }

    async def sync_all(self, mode: str = "FULL") -> list[dict[str, Any]]:
        """Full/academic-tree sync in dependency order (parents before children)."""
        order = ["board", "school", "session", "class", "subject", "chapter", "unit", "topic"]
        results = []
        for entity_type in order:
            try:
                results.append(await self.sync_entity_type(entity_type, mode=mode))
            except Exception as exc:  # noqa: BLE001 - one entity failing must not abort the rest
                logger.error("erp.sync.entity_failed", entity_type=entity_type, error=str(exc))
                results.append(
                    {"entity_type": entity_type, "status": "FAILED", "error": str(exc)}
                )
        return results

    # ------------------------------------------------------------------
    # Sync status / logs
    # ------------------------------------------------------------------

    async def get_sync_status(self) -> dict[str, Any]:
        """Last sync run per entity type + ERP config state (Phase 16 §7)."""
        entity_types = list(_entity_config().keys())
        per_entity = {}
        for et in entity_types:
            last = await self.log_repo.get_last_for_entity(et)
            if last:
                per_entity[et] = {
                    "status": last.status,
                    "sync_type": last.sync_type,
                    "records_pulled": last.records_pulled,
                    "records_updated": last.records_updated,
                    "records_failed": last.records_failed,
                    "started_at": last.started_at.isoformat(),
                    "completed_at": last.completed_at.isoformat() if last.completed_at else None,
                }
        return {
            "erp_configured": self.client.is_configured,
            "erp_base_url": self.client.base_url,
            "per_entity": per_entity,
        }

    async def get_sync_logs(
        self, *, entity_type: str | None = None, limit: int = 50
    ) -> list[dict[str, Any]]:
        """Audit log entries for inbound sync runs (Phase 16 §7)."""
        runs = await self.log_repo.list_runs(entity_type=entity_type, limit=limit)
        return [
            {
                "id": str(r.public_id),
                "sync_type": r.sync_type,
                "entity_type": r.entity_type,
                "status": r.status,
                "records_pulled": r.records_pulled,
                "records_updated": r.records_updated,
                "records_failed": r.records_failed,
                "error_detail": r.error_detail,
                "started_at": r.started_at.isoformat(),
                "completed_at": r.completed_at.isoformat() if r.completed_at else None,
            }
            for r in runs
        ]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _upsert_record(
        self, model: type[Any], fks: dict[str, str], item: dict[str, Any]
    ) -> int:
        """Upsert one ERP record into the snapshot table. Returns 1 if changed/created."""
        erp_id = str(item.get("erp_id"))
        if not erp_id:
            return 0

        existing = (
            await self.session.execute(
                select(model).where(model.erp_id == erp_id)  # type: ignore[attr-defined]
            )
        ).scalar_one_or_none()

        data: dict[str, Any] = {"erp_id": erp_id}
        for field, value in item.items():
            if field in ("erp_id", "updated_at", "is_deleted"):
                continue
            if field in fks:
                # Resolve parent erp_id → local PK; if the parent hasn't been
                # synced yet (or was deleted), skip the FK (best effort).
                parent_erp_id = value
                if parent_erp_id:
                    resolved = await self._resolve_erp_id(fks[field], str(parent_erp_id))
                    if resolved is not None:
                        data[fks[field]] = resolved
                continue
            if hasattr(model, field):
                data[field] = self._coerce_value(model, field, value)

        data["sync_status"] = "SYNCED"
        data["synced_at"] = datetime.now(tz=timezone.utc)

        if existing is not None:
            for key, value in data.items():
                setattr(existing, key, value)
            if item.get("is_deleted"):
                existing.is_deleted = True
            else:
                existing.is_deleted = False
            await self.session.flush()
            return 1

        instance = model(**data)
        if item.get("is_deleted"):
            instance.is_deleted = True
        self.session.add(instance)
        await self.session.flush()
        return 1

    async def _resolve_erp_id(self, local_fk: str, erp_id: str) -> int | None:
        """Map an ERP erp_id to the local PK of a parent snapshot row."""
        fk_to_model = {
            "board_id": Board,
            "school_id": School,
            "class_id": Class,
            "subject_id": Subject,
            "chapter_id": Chapter,
            "unit_id": Unit,
        }
        model = fk_to_model.get(local_fk)
        if model is None:
            return None
        row = (
            await self.session.execute(
                select(model.id).where(model.erp_id == erp_id, model.is_deleted.is_(False))
            )
        ).scalar_one_or_none()
        return row

    def _coerce_value(self, model: type[Any], field: str, value: Any) -> Any:
        """Coerce a raw ERP payload value to the target column's Python type.

        ERP sends plain JSON scalars (dates as "YYYY-MM-DD" strings, etc.);
        SQLAlchemy maps them onto typed columns (Date/Boolean/...) that reject
        the raw string at the driver level, so convert here before binding.
        """
        if value is None:
            return None
        col = getattr(model.__table__.c, field, None)
        if col is None:
            return value
        if isinstance(col.type, Date):
            if isinstance(value, (datetime, date)):
                return value.date() if isinstance(value, datetime) else value
            if isinstance(value, str):
                return date.fromisoformat(value)
        return value

    async def _mark_missing(
        self, model: type[Any], entity_type: str, pulled: int
    ) -> None:
        """Full-sync: flag previously-synced rows missing from the ERP response.

        Only rows already carrying `sync_status='SYNCED'` are eligible; rows that
        were never synced (e.g. manually created) are left untouched.
        """
        # We can't easily know which erp_ids were just pulled without tracking
        # them; simplest safe approximation: if nothing was pulled, don't run.
        if pulled == 0:
            return
        now = datetime.now(tz=timezone.utc)
        stmt = (
            select(model)
            .where(model.is_deleted.is_(False))
            .where(model.sync_status == "SYNCED")  # type: ignore[attr-defined]
            .where(model.synced_at.isnot(None))  # type: ignore[attr-defined]
        )
        rows = (await self.session.execute(stmt)).scalars().all()
        # Only mark rows that were synced *before* this run began (i.e. not the
        # ones upserted by the current run). Rows upserted just now have a very
        # recent synced_at; we conservatively require > 60s age to avoid
        # clobbering fresh rows with same-epoch timestamps.
        for row in rows:
            if row.synced_at and (now - row.synced_at).total_seconds() > 60:
                row.sync_status = "MISSING_IN_ERP"  # type: ignore[attr-defined]
        await self.session.flush()
