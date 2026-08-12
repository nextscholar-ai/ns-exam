"""
Business vocabulary shared across modules. Deliberately kept tiny (Phase 5 §9) -
this is NOT a dumping ground for module-specific enums (those live inside each
module's own models.py/schemas.py).
"""
from __future__ import annotations

from enum import StrEnum


class UserType(StrEnum):
    SUPER_ADMIN = "SUPER_ADMIN"
    ADMIN = "ADMIN"
    SCHOOL_ADMIN = "SCHOOL_ADMIN"
    TEACHER = "TEACHER"
    ERP_STUDENT = "ERP_STUDENT"
    EXTERNAL_STUDENT = "EXTERNAL_STUDENT"
    GUEST_STUDENT = "GUEST_STUDENT"


class ExamType(StrEnum):
    """Exactly two values per Phase 1 §13 explicit ruling - Recovery is a
    recommendation output, never a distinct exam type."""

    REGULAR = "REGULAR"
    MOCK = "MOCK"


class SyncStatus(StrEnum):
    SYNCED = "SYNCED"
    STALE = "STALE"
    MISSING_IN_ERP = "MISSING_IN_ERP"


class RecordStatus(StrEnum):
    """Generic lifecycle status reused by multiple modules where it fits
    (each module may still define a narrower status enum of its own)."""

    DRAFT = "DRAFT"
    PUBLISHED = "PUBLISHED"
    ARCHIVED = "ARCHIVED"
