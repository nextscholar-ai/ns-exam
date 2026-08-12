"""
Evaluation Engine module — Domain Events (Phase 13 §12 / Phase 17 §3).

Real event publishers dispatching through `app.core.events.bus.event_bus`.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

from app.core.events.bus import event_bus
from app.core.events.event_names import EVALUATION_COMPLETED, OMR_EVALUATED, SUBJECTIVE_EVALUATED


@dataclass(frozen=True)
class OMREvaluated:
    omr_upload_id: int
    attempt_id: int
    confidence_score: float
    status: str


@dataclass(frozen=True)
class SubjectiveEvaluated:
    evaluation_id: int
    teacher_id: int | None


@dataclass(frozen=True)
class EvaluationCompleted:
    evaluation_public_id: str
    attempt_id: int
    total_marks: float
    percentage: float
    result_status: str


async def publish_omr_evaluated(event: OMREvaluated) -> None:
    await event_bus.publish(OMR_EVALUATED, asdict(event))


async def publish_subjective_evaluated(event: SubjectiveEvaluated) -> None:
    await event_bus.publish(SUBJECTIVE_EVALUATED, asdict(event))


async def publish_evaluation_completed(event: EvaluationCompleted) -> None:
    await event_bus.publish(EVALUATION_COMPLETED, asdict(event))
