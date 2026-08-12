"""
Exam-Engine JWT — the ONE token format every module trusts (Phase 6 §6.3).

Regardless of how a user proved identity (ERP validation, local password,
guest start), Exam Engine issues its own JWT with this exact claim shape, so
downstream modules never deal with three different token formats.

Claims:
    sub          users.public_id (UUID string) — never the internal BIGINT id
    user_type    from users.user_type
    auth_source  ERP | LOCAL | GUEST
    school_id    internal BIGINT, nullable
    board_id     internal BIGINT, nullable
    roles        list[str] of role codes
    exp          access: 30 min normal / 4h guest
    jti          token id (for refresh/revocation tracking)
"""
from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from jose import JWTError, jwt

from app.core.config import settings
from app.core.exceptions import UnauthorizedError

ACCESS_TOKEN_TYPE = "access"
GUEST_ACCESS_TOKEN_EXPIRE_HOURS = 4


def create_access_token(
    *,
    public_id: str,
    user_type: str,
    auth_source: str,
    roles: list[str],
    school_id: int | None = None,
    board_id: int | None = None,
    is_guest: bool = False,
) -> tuple[str, str]:
    """Returns (token, jti). Guest tokens get a 4h expiry (Phase 6 §6.3);
    everyone else gets the standard access-token TTL from settings."""
    jti = str(uuid.uuid4())
    if is_guest:
        expire = datetime.now(timezone.utc) + timedelta(hours=GUEST_ACCESS_TOKEN_EXPIRE_HOURS)
    else:
        expire = datetime.now(timezone.utc) + timedelta(
            minutes=settings.jwt.access_token_expire_minutes
        )

    payload: dict[str, Any] = {
        "sub": public_id,
        "user_type": user_type,
        "auth_source": auth_source,
        "school_id": school_id,
        "board_id": board_id,
        "roles": roles,
        "exp": expire,
        "jti": jti,
        "type": ACCESS_TOKEN_TYPE,
    }
    token = jwt.encode(payload, settings.jwt.secret, algorithm=settings.jwt.algorithm)
    return token, jti


def decode_access_token(token: str) -> dict[str, Any]:
    try:
        claims = jwt.decode(token, settings.jwt.secret, algorithms=[settings.jwt.algorithm])
    except JWTError as exc:
        raise UnauthorizedError("Invalid or expired token") from exc

    if claims.get("type") != ACCESS_TOKEN_TYPE:
        raise UnauthorizedError("Token is not an access token")
    return claims


def generate_refresh_token() -> tuple[str, str]:
    """
    Refresh tokens are opaque random strings (NOT JWTs) — only their SHA-256
    hash is ever stored (Phase 6 §6.3 / Phase 4 §12). Returns (raw_token, hash)
    - the raw token is returned to the client once and never persisted.
    """
    raw_token = secrets.token_urlsafe(48)
    return raw_token, hash_refresh_token(raw_token)


def hash_refresh_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
