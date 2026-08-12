"""
Identity module router (Phase 6 §9). Thin - delegates immediately to
IdentityService. This is the module every other module's `get_current_user`
dependency ultimately trusts.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.session import get_db
from app.core.exceptions import UnauthorizedError
from app.core.security.rbac import CurrentUser, get_current_user
from app.modules.identity.schemas import (
    GuestStartRequest,
    GuestTokenResponse,
    LocalLoginRequest,
    LocalRegisterRequest,
    RefreshRequest,
    TokenResponse,
    UserMeResponse,
)
from app.modules.identity.service import IdentityService

router = APIRouter(prefix="/identity", tags=["identity"])


@router.get("/ping")
async def ping() -> dict[str, str]:
    return {"module": "identity", "status": "ok"}


@router.post("/auth/erp/login", response_model=TokenResponse)
async def erp_login(
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """Client sends the ERP-issued token via `Authorization: Bearer <erp_token>`
    (Phase 6 §6.1) - NOT the Exam-Engine JWT."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise UnauthorizedError("Missing ERP token in Authorization header")
    erp_token = authorization.split(" ", 1)[1]

    service = IdentityService(db)
    erp_result = await service.validate_erp_token(erp_token)
    user = await service.upsert_erp_user(erp_result)
    tokens = await service.issue_tokens(user)
    return TokenResponse(
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        expires_in_seconds=tokens.expires_in_seconds,
    )


@router.post("/auth/local/register", response_model=TokenResponse, status_code=201)
async def local_register(
    payload: LocalRegisterRequest, db: AsyncSession = Depends(get_db)
) -> TokenResponse:
    service = IdentityService(db)
    user = await service.register_external_student(payload)
    tokens = await service.issue_tokens(user)
    return TokenResponse(
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        expires_in_seconds=tokens.expires_in_seconds,
    )


@router.post("/auth/local/login", response_model=TokenResponse)
async def local_login(
    payload: LocalLoginRequest, db: AsyncSession = Depends(get_db)
) -> TokenResponse:
    service = IdentityService(db)
    user = await service.authenticate_local(payload)
    tokens = await service.issue_tokens(user)
    return TokenResponse(
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        expires_in_seconds=tokens.expires_in_seconds,
    )


@router.post("/auth/guest/start", response_model=GuestTokenResponse, status_code=201)
async def guest_start(
    payload: GuestStartRequest, db: AsyncSession = Depends(get_db)
) -> GuestTokenResponse:
    service = IdentityService(db)
    user, guest_pin = await service.start_guest_session(payload)
    tokens = await service.issue_tokens(user, is_guest=True)
    return GuestTokenResponse(
        access_token=tokens.access_token,
        expires_in_seconds=tokens.expires_in_seconds,
        guest_pin=guest_pin,
    )


@router.post("/auth/refresh", response_model=TokenResponse)
async def refresh_token(
    payload: RefreshRequest, db: AsyncSession = Depends(get_db)
) -> TokenResponse:
    service = IdentityService(db)
    tokens = await service.refresh(payload.refresh_token)
    return TokenResponse(
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        expires_in_seconds=tokens.expires_in_seconds,
    )


@router.post("/auth/logout", status_code=204)
async def logout(
    payload: RefreshRequest,
    db: AsyncSession = Depends(get_db),
    _current_user: CurrentUser = Depends(get_current_user),
) -> None:
    service = IdentityService(db)
    await service.logout(payload.refresh_token)


@router.get("/auth/me", response_model=UserMeResponse)
async def me(current_user: CurrentUser = Depends(get_current_user)) -> UserMeResponse:
    """Returns current user profile from token claims (Phase 6 §9) - no
    additional DB read needed since claims already carry everything."""
    return UserMeResponse(
        public_id=current_user.public_id,
        email=None,  # not carried in claims by design - fetch via a future /me/profile if needed
        name=None,
        user_type=current_user.user_type,
        auth_source=current_user.auth_source,
        roles=current_user.roles,
        school_id=current_user.school_id,
        board_id=current_user.board_id,
    )
