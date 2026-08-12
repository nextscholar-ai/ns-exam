"""
Blueprint module — Domain events (Phase 11 §11).

Events are thin data containers; publishing is fire-and-forget.
Phase 17 (Background Jobs) wires these to actual queues.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BlueprintActivated:
    """Fired when a Blueprint transitions DRAFT → ACTIVE."""

    blueprint_public_id: str
    board_id: int
    board_name: str | None = None


@dataclass(frozen=True)
class ExamConfigCreated:
    """Fired when an ExamConfiguration is created."""

    exam_config_public_id: str
    blueprint_public_id: str
    exam_type: str
    personalized: bool


async def publish_blueprint_activated(event: BlueprintActivated) -> None:
    """Publish BlueprintActivated — Phase 17 replaces this stub with a real queue."""
    pass  # noqa: SIM113


async def publish_exam_config_created(event: ExamConfigCreated) -> None:
    """Publish ExamConfigCreated — stub for Phase 17."""
    pass  # noqa: SIM113
