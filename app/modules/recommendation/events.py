"""
Recommendation Engine module — Domain Events (Phase 15 §11 / Phase 17 §3).

Real event publishers dispatching through `app.core.events.bus.event_bus`.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

from app.core.events.bus import event_bus
from app.core.events.event_names import RECOMMENDATION_GENERATED


@dataclass(frozen=True)
class RecommendationGenerated:
    recommendation_public_id: str
    student_id: int
    subject_id: int
    recommendation_type: str
    target_topic_ids: list[int]
    priority_score: float


async def publish_recommendation_generated(event: RecommendationGenerated) -> None:
    await event_bus.publish(RECOMMENDATION_GENERATED, asdict(event))
