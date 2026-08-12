"""
Recommendation Engine domain — State Machine (Phase 15 §5).

Enforces strict recommendation lifecycle state transitions:
RECOMMENDED → ACCEPTED → IN_PROGRESS → COMPLETED
RECOMMENDED → DISMISSED
RECOMMENDED → EXPIRED
ACCEPTED → DISMISSED
IN_PROGRESS → COMPLETED

Invalid transitions raise a BusinessRuleError.
"""
from __future__ import annotations

from app.core.exceptions import BusinessRuleError

# Allowed recommendation status transitions
RECOMMENDATION_TRANSITIONS: dict[str, set[str]] = {
    "RECOMMENDED": {"ACCEPTED", "DISMISSED", "EXPIRED"},
    "ACCEPTED": {"IN_PROGRESS", "DISMISSED", "COMPLETED"},
    "IN_PROGRESS": {"COMPLETED", "DISMISSED"},
    "COMPLETED": set(),   # Terminal state
    "DISMISSED": set(),   # Terminal state
    "EXPIRED": set(),     # Terminal state
}


def validate_recommendation_transition(current_state: str, target_state: str) -> None:
    """
    Validates recommendation status transition.
    Raises BusinessRuleError if transition is illegal.
    """
    if current_state == target_state:
        return

    allowed = RECOMMENDATION_TRANSITIONS.get(current_state, set())
    if target_state not in allowed:
        raise BusinessRuleError(
            f"Illegal recommendation transition: cannot transition from '{current_state}' to '{target_state}'"
        )
