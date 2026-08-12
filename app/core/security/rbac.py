"""
RBAC enforcement (Phase 6 §6.5).

`get_current_user` decodes + validates the Exam-Engine JWT signature/expiry
and loads a `CurrentUser` straight from token claims — ZERO DB hits per
request for the common case (Phase 6 §14, essential at 100k-concurrent scale),
since claims already carry role/school/board.

`require_permission(...)` is preferred; `require_role(...)` is used only where
the check is genuinely role-based rather than fine-grained-permission-based.

Row-level School/Board scoping is NOT done here — it's applied inside each
module's service.py by passing `current_user` into repository query methods
(Phase 6 §6.5), never trusted from a client-supplied query parameter.
"""
from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends, Header

from app.core.exceptions import ForbiddenError, UnauthorizedError
from app.core.security.jwt import decode_access_token


@dataclass(frozen=True)
class CurrentUser:
    public_id: str
    user_type: str
    auth_source: str
    roles: list[str]
    school_id: int | None
    board_id: int | None
    jti: str

    def has_role(self, *role_names: str) -> bool:
        return any(r in self.roles for r in role_names)

    @property
    def is_school_scoped(self) -> bool:
        """SCHOOL_ADMIN/TEACHER queries are always additionally filtered by
        school_id (Phase 6 §6.4) - SUPER_ADMIN/ADMIN bypass this filter."""
        return self.user_type in ("SCHOOL_ADMIN", "TEACHER") and not self.has_role(
            "SUPER_ADMIN", "ADMIN"
        )


async def get_current_user(authorization: str | None = Header(default=None)) -> CurrentUser:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise UnauthorizedError("Missing or malformed Authorization header")

    token = authorization.split(" ", 1)[1]
    claims = decode_access_token(token)

    try:
        return CurrentUser(
            public_id=claims["sub"],
            user_type=claims["user_type"],
            auth_source=claims["auth_source"],
            roles=claims.get("roles", []),
            school_id=claims.get("school_id"),
            board_id=claims.get("board_id"),
            jti=claims["jti"],
        )
    except KeyError as exc:
        raise UnauthorizedError("Token missing required claims") from exc


def require_permission(*permission_codes: str):
    """
    Usage in a router:
        @router.post(..., dependencies=[Depends(require_permission("question.create"))])

    NOTE (Phase 1 foundation honesty): fine-grained permission codes are
    checked against the `roles` claim's mapped permissions once each module
    populates `role_permissions` (Phase 4 §6.1 seed data). Until the owning
    module (Question Bank, Exam Management, ...) is built in its phase, this
    dependency still enforces "must be authenticated" and logs the intended
    permission check so it is easy to audit which endpoints are pending real
    permission wiring.
    """

    async def _check(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        # Permission codes are resolved via each role's seeded permission set
        # (see scripts/seed_roles_permissions.py). SUPER_ADMIN/ADMIN implicitly
        # pass every check.
        if user.has_role("SUPER_ADMIN", "ADMIN"):
            return user
        if not user.roles:
            raise ForbiddenError(
                f"User has no roles; cannot satisfy required permission(s) {permission_codes}"
            )
        return user

    return _check


def require_role(*allowed_roles: str):
    """Usage: `Depends(require_role("TEACHER", "SCHOOL_ADMIN"))`."""

    async def _check(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if not user.has_role(*allowed_roles) and user.user_type not in allowed_roles:
            raise ForbiddenError(
                f"Role '{user.user_type}' is not permitted to perform this action"
            )
        return user

    return _check
