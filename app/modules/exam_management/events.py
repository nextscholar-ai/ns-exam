"""
Exam Management module — Domain Events (Phase 12 §10 / Phase 17 §3).

Real event publishers dispatching through `app.core.events.bus.event_bus`.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

from app.core.events.bus import event_bus
from app.core.events.event_names import EXAM_PUBLISHED, EXAM_SUBMITTED


@dataclass(frozen=True)
class ExamPublished:
    exam_public_id: str
    board_id: int
    school_id: int
    join_code: str | None


@dataclass(frozen=True)
class ExamSubmitted:
    attempt_public_id: str
    exam_id: int
    student_id: int
    paper_id: int
    submitted_at: str


async def publish_exam_published(event: ExamPublished) -> None:
    await event_bus.publish(EXAM_PUBLISHED, asdict(event))


async def publish_exam_submitted(event: ExamSubmitted) -> None:
    await event_bus.publish(EXAM_SUBMITTED, asdict(event))
