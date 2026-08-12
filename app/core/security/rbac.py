"""
Permission-check FastAPI dependencies.

Phase 1 skeleton: decodes the bearer token into a lightweight `CurrentUser` and
exposes `require_roles(...)` for endpoint-level RBAC. Phase 6 (Authentication &
RBAC) replaces the token-claims-only resolution with a full DB-backed identity
lookup (permissions table, role hierarchy) - the *dependency signature* used by
routers stays the same so no router code needs to change later.
"""
from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends, Header

from app.core.exceptions import ForbiddenError, UnauthorizedError
from app.core.security.jwt import decode_token
from app.shared.enums import UserType


@dataclass(frozen=True)
class CurrentUser:
    id: int
    public_id: str
    user_type: UserType


async def get_current_user(authorization: str | None = Header(default=None)) -> CurrentUser:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise UnauthorizedError("Missing or malformed Authorization header")

    token = authorization.split(" ", 1)[1]
    claims = decode_token(token)

    try:
        return CurrentUser(
            id=int(claims["sub"]),
            public_id=claims.get("public_id", ""),
            user_type=UserType(claims["user_type"]),
        )
    except (KeyError, ValueError) as exc:
        raise UnauthorizedError("Token missing required claims") from exc


def require_roles(*allowed: UserType):
    """
    Usage: `current_user: CurrentUser = Depends(require_roles(UserType.ADMIN, UserType.TEACHER))`
    """

    async def _check(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if user.user_type not in allowed:
            raise ForbiddenError(
                f"Role '{user.user_type}' is not permitted to perform this action"
            )
        return user

    return _check
