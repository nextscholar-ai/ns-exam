"""
Shared test helpers for role-based API tests.

Provides token generation for every role and common fixture patterns so
no code is duplicated across test files.
"""
from __future__ import annotations

from app.core.security.jwt import create_access_token


# ---------------------------------------------------------------------------
# Token factory — single source of truth for test tokens
# ---------------------------------------------------------------------------

def make_token(
    *,
    public_id: str = "00000000-0000-0000-0000-000000000001",
    user_type: str,
    auth_source: str = "LOCAL",
    roles: list[str] | None = None,
    school_id: int | None = None,
    board_id: int | None = None,
    is_guest: bool = False,
) -> str:
    """Create a valid JWT for testing. Returns only the access token string."""
    token, _ = create_access_token(
        public_id=public_id,
        user_type=user_type,
        auth_source=auth_source,
        roles=roles or [],
        school_id=school_id,
        board_id=board_id,
        is_guest=is_guest,
    )
    return token


# Convenience builders for each role

def super_admin_token(**overrides) -> str:
    defaults = dict(user_type="SUPER_ADMIN", roles=["SUPER_ADMIN"], auth_source="LOCAL")
    defaults.update(overrides)
    return make_token(**defaults)


def admin_token(**overrides) -> str:
    defaults = dict(user_type="ADMIN", roles=["ADMIN"], auth_source="LOCAL")
    defaults.update(overrides)
    return make_token(**defaults)


def school_admin_token(school_id: int = 1, board_id: int = 1, **overrides) -> str:
    defaults = dict(
        user_type="SCHOOL_ADMIN",
        roles=["SCHOOL_ADMIN"],
        auth_source="ERP",
        school_id=school_id,
        board_id=board_id,
    )
    defaults.update(overrides)
    return make_token(**defaults)


def teacher_token(school_id: int = 1, board_id: int = 1, **overrides) -> str:
    defaults = dict(
        user_type="TEACHER",
        roles=["TEACHER"],
        auth_source="ERP",
        school_id=school_id,
        board_id=board_id,
    )
    defaults.update(overrides)
    return make_token(**defaults)


def erp_student_token(school_id: int = 1, board_id: int = 1, **overrides) -> str:
    defaults = dict(
        user_type="ERP_STUDENT",
        roles=["STUDENT"],
        auth_source="ERP",
        school_id=school_id,
        board_id=board_id,
    )
    defaults.update(overrides)
    return make_token(**defaults)


def external_student_token(**overrides) -> str:
    defaults = dict(
        user_type="EXTERNAL_STUDENT",
        roles=["STUDENT"],
        auth_source="LOCAL",
    )
    defaults.update(overrides)
    return make_token(**defaults)


def guest_token(**overrides) -> str:
    defaults = dict(
        user_type="GUEST_STUDENT",
        roles=[],
        auth_source="GUEST",
        is_guest=True,
    )
    defaults.update(overrides)
    return make_token(**defaults)


# ---------------------------------------------------------------------------
# Auth header builder
# ---------------------------------------------------------------------------

def auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}
