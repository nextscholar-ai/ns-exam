"""
Question Bank domain logic - Versioning & Evolution.

Handles building immutable JSON snapshots of question states and tracking
question_group_id evolution across versions.
"""
from __future__ import annotations

from typing import Any


def create_question_snapshot(
    question_type: str,
    question_data: dict[str, Any],
) -> dict[str, Any]:
    """Builds a clean, serializable JSON snapshot of a question at a given version."""
    excluded_keys = {"_sa_instance_state", "id", "created_at", "updated_at", "deleted_at", "deleted_by"}
    snapshot = {k: v for k, v in question_data.items() if k not in excluded_keys}
    snapshot["question_type"] = question_type
    return snapshot


def increment_version(current_version_no: int) -> int:
    """Returns next incremental version number."""
    return current_version_no + 1
