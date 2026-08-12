"""
Local JWT issuance/verification - used ONLY for External Students and Guest
Students (Phase 1 §5 ownership matrix: Exam Engine owns local auth only for
these two actor types). ERP users are authenticated via `erp_auth.py` instead.

Full login/refresh/RBAC flows are built out in Phase 6; this module provides
the low-level encode/decode primitives so `core/security/rbac.py` and Phase 6's
`identity` module have a stable dependency from Phase 1 onward.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from jose import JWTError, jwt

from app.core.config import settings
from app.core.exceptions import UnauthorizedError


def create_access_token(subject: str, extra_claims: dict[str, Any] | None = None) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.jwt.access_token_expire_minutes
    )
    payload: dict[str, Any] = {"sub": subject, "exp": expire, "type": "access"}
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, settings.jwt.secret, algorithm=settings.jwt.algorithm)


def create_refresh_token(subject: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=settings.jwt.refresh_token_expire_days)
    payload = {"sub": subject, "exp": expire, "type": "refresh"}
    return jwt.encode(payload, settings.jwt.secret, algorithm=settings.jwt.algorithm)


def decode_token(token: str) -> dict[str, Any]:
    try:
        return jwt.decode(token, settings.jwt.secret, algorithms=[settings.jwt.algorithm])
    except JWTError as exc:
        raise UnauthorizedError("Invalid or expired token") from exc
