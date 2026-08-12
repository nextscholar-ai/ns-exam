"""
Evaluation Engine domain — State Machine (Phase 13 §5).

Enforces strict evaluation lifecycle state transitions:
PENDING → STARTED → OBJECTIVE_COMPLETED → SUBJECTIVE_PENDING → COMPLETED → LOCKED → PUBLISHED

Invalid state transitions raise a BusinessRuleError.
"""
from __future__ import annotations

from app.core.exceptions import BusinessRuleError

# Allowed evaluation transitions: {current_state: set(allowed_next_states)}
EVALUATION_TRANSITIONS: dict[str, set[str]] = {
    "PENDING": {"STARTED", "OBJECTIVE_COMPLETED", "SUBJECTIVE_PENDING"},
    "STARTED": {"OBJECTIVE_COMPLETED", "SUBJECTIVE_PENDING", "COMPLETED"},
    "OBJECTIVE_COMPLETED": {"SUBJECTIVE_PENDING", "COMPLETED"},
    "SUBJECTIVE_PENDING": {"COMPLETED"},
    "COMPLETED": {"LOCKED", "STARTED"},  # Can return to STARTED if re-eval unlocked
    "LOCKED": {"PUBLISHED", "STARTED"},   # Returning to STARTED requires re-evaluation approval
    "PUBLISHED": {"STARTED"},             # Admin unlock required
}


def validate_evaluation_transition(current_state: str, target_state: str) -> None:
    """
    Validates evaluation status transition.
    Raises BusinessRuleError if transition is illegal.
    """
    if current_state == target_state:
        return

    allowed = EVALUATION_TRANSITIONS.get(current_state, set())
    if target_state not in allowed:
        raise BusinessRuleError(
            f"Illegal evaluation transition: cannot transition evaluation from '{current_state}' to '{target_state}'"
        )
