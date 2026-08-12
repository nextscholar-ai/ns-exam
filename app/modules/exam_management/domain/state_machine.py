"""
Exam Management domain — Strict State Machine (Phase 12 §5).

Enforces the canonical exam lifecycle:
DRAFT → CONFIGURED → PAPER_GENERATED → TEACHER_REVIEWING → APPROVED
   → PUBLISHED → SCHEDULED → ACTIVE → COMPLETED
   → EVALUATING → RESULT_PUBLISHED → ARCHIVED

No illegal state jumps are allowed. Any attempt to write an invalid transition
raises a BusinessRuleError.
"""
from __future__ import annotations

from typing import Any

from app.core.exceptions import BusinessRuleError

# State transition table: {current_state: set(allowed_next_states)}
EXAM_TRANSITIONS: dict[str, set[str]] = {
    "DRAFT": {"CONFIGURED", "ARCHIVED"},
    "CONFIGURED": {"PAPER_GENERATED", "DRAFT", "ARCHIVED"},
    "PAPER_GENERATED": {"TEACHER_REVIEWING", "CONFIGURED", "ARCHIVED"},
    "TEACHER_REVIEWING": {"APPROVED", "PAPER_GENERATED", "ARCHIVED"},
    "APPROVED": {"PUBLISHED", "TEACHER_REVIEWING", "ARCHIVED"},
    "PUBLISHED": {"SCHEDULED", "ACTIVE", "ARCHIVED"},
    "SCHEDULED": {"ACTIVE", "PUBLISHED", "ARCHIVED"},
    "ACTIVE": {"COMPLETED", "ARCHIVED"},
    "COMPLETED": {"EVALUATING", "ARCHIVED"},
    "EVALUATING": {"RESULT_PUBLISHED", "ARCHIVED"},
    "RESULT_PUBLISHED": {"ARCHIVED"},
    "ARCHIVED": set(),
}


def validate_transition(current_state: str, target_state: str) -> None:
    """
    Validates if transitioning from current_state to target_state is allowed.

    Raises BusinessRuleError if transition is invalid.
    """
    if current_state == target_state:
        return  # No-op / idempotent

    allowed = EXAM_TRANSITIONS.get(current_state, set())
    if target_state not in allowed:
        raise BusinessRuleError(
            f"Illegal state transition: cannot transition exam from '{current_state}' to '{target_state}'"
        )
