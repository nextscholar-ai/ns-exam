"""
Paper Generation module — Domain Events (Phase 11 §11 / Phase 17 §3).

Real event publishers dispatching through `app.core.events.bus.event_bus`.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

from app.core.events.bus import event_bus
from app.core.events.event_names import PAPER_APPROVED, PAPER_GENERATED


@dataclass(frozen=True)
class PaperGenerated:
    paper_public_id: str
    exam_configuration_id: int
    student_id: int | None
    status: str   # GENERATED or NEEDS_ATTENTION
    total_marks: float


@dataclass(frozen=True)
class PaperApproved:
    paper_public_id: str
    exam_configuration_id: int
    approved_by: str | None


async def publish_paper_generated(event: PaperGenerated) -> None:
    await event_bus.publish(PAPER_GENERATED, asdict(event))


async def publish_paper_approved(event: PaperApproved) -> None:
    await event_bus.publish(PAPER_APPROVED, asdict(event))
