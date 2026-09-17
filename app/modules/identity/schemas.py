"""Identity module — request/response schemas (Phase 6 §9)."""
from __future__ import annotations

import re

from pydantic import BaseModel, EmailStr, field_validator

_PASSWORD_MIN_LEN = 8
_PASSWORD_DIGIT_RE = re.compile(r"\d")


class LocalRegisterRequest(BaseModel):
    """External Student self-registration (Phase 6 §6.2)."""

    email: EmailStr
    password: str
    name: str
    phone: str | None = None

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, value: str) -> str:
        """Phase 6 §12: min 8 chars, at least 1 digit — enforced here, not
        just documented."""
        if len(value) < _PASSWORD_MIN_LEN:
            raise ValueError(f"Password must be at least {_PASSWORD_MIN_LEN} characters")
        if not _PASSWORD_DIGIT_RE.search(value):
            raise ValueError("Password must contain at least one digit")
        return value


class LocalLoginRequest(BaseModel):
    email: EmailStr
    password: str


class ERPCredentialsLoginRequest(BaseModel):
    """ERP login with email/phone + password (not token-based)."""
    identifier: str  # email or phone
    password: str


class ERPTokenLoginRequest(BaseModel):
    """ERP login with token in body (optional fallback if Authorization header not used)."""
    token: str | None = None


class GuestStartRequest(BaseModel):
    name: str
    school_hint: str | None = None  # free-text, not FK-validated - guest may have no school


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str | None = None  # None for guest sessions (Phase 6 §6.3)
    token_type: str = "bearer"
    expires_in_seconds: int


class GuestTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in_seconds: int
    guest_pin: str  # shown once at guest-start, used for exam-flow re-auth (Phase 6 §6.3)


class UserMeResponse(BaseModel):
    public_id: str
    email: str | None
    name: str | None
    user_type: str
    auth_source: str
    roles: list[str]
    school_id: int | None
    board_id: int | None
