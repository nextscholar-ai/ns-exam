"""
Reporting Engine domain — State Machine (Phase 16 §5).

Enforces strict report snapshot lifecycle state transitions:
GENERATED → PUBLISHED → ARCHIVED
"""
from __future__ import annotations

from app.core.exceptions import BusinessRuleError

# Allowed report transitions
REPORT_TRANSITIONS: dict[str, set[str]] = {
    "GENERATED": {"PUBLISHED", "ARCHIVED"},
    "PUBLISHED": {"ARCHIVED"},
    "ARCHIVED": set(),
}


def validate_report_transition(current_state: str, target_state: str) -> None:
    """
    Validates report status transition.
    Raises BusinessRuleError if transition is illegal.
    """
    if current_state == target_state:
        return

    allowed = REPORT_TRANSITIONS.get(current_state, set())
    if target_state not in allowed:
        raise BusinessRuleError(
            f"Illegal report transition: cannot transition report from '{current_state}' to '{target_state}'"
        )
