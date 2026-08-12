"""
Reporting Engine module — Domain Events (Phase 16 §11.5 / Phase 17 §3).

Real event publishers dispatching through `app.core.events.bus.event_bus`.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

from app.core.events.bus import event_bus
from app.core.events.event_names import REPORT_GENERATED


@dataclass(frozen=True)
class ReportGenerated:
    report_public_id: str
    report_type: str
    student_id: int | None
    exam_id: int | None


async def publish_report_generated(event: ReportGenerated) -> None:
    await event_bus.publish(REPORT_GENERATED, asdict(event))
