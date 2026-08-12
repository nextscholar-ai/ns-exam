"""
IdentityService (Phase 6 §10) — all business logic for authentication lives
here. Routers delegate immediately; repositories only do DB access.
"""
from __future__ import annotations

import secrets
import string
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from app.core.config import settings
from app.core.db.base_model import utcnow
from app.core.db.session import DbSession
from app.core.events.bus import event_bus
from app.core.exceptions import ConflictError, UnauthorizedError
from app.core.logging import get_logger
from app.core.security.erp_auth import ERPValidationResult, erp_auth_client
from app.core.security.jwt import (
    create_access_token,
    generate_refresh_token,
    hash_refresh_token,
)
from app.core.security.password import hash_password, verify_password
from app.modules.identity.models import RefreshToken, User, UserRole
from app.modules.identity.repository import (
    LoginHistoryRepository,
    RefreshTokenRepository,
    RoleRepository,
    UserRepository,
)
from app.modules.identity.schemas import (
    GuestStartRequest,
    LocalLoginRequest,
    LocalRegisterRequest,
)

logger = get_logger(__name__)

GUEST_RETENTION_DAYS = 45
REFRESH_TOKEN_EXPIRE_DAYS = settings.jwt.refresh_token_expire_days

# Local event names for Identity - internal only, follow the same bus mechanism
# as the Phase 2 canonical chain but aren't part of it (Phase 6 §18).
USER_REGISTERED = "UserRegistered"
USER_LOGGED_IN = "UserLoggedIn"
USER_LOGGED_OUT = "UserLoggedOut"


@dataclass(frozen=True)
class IssuedTokens:
    access_token: str
    refresh_token: str | None
    expires_in_seconds: int


class IdentityService:
    def __init__(self, session: DbSession) -> None:
        self.session = session
        self.users = UserRepository(session)
        self.roles = RoleRepository(session)
        self.refresh_tokens = RefreshTokenRepository(session)
        self.login_history = LoginHistoryRepository(session)

    # ---------------------------------------------------------------- ERP --
    async def validate_erp_token(self, erp_token: str) -> ERPValidationResult:
        return await erp_auth_client.validate_token(erp_token)

    async def upsert_erp_user(self, erp_result: ERPValidationResult) -> User:
        """Find-or-create the `users` row for an ERP-authenticated user
        (Phase 6 §6.1). School/board id resolution against snapshot tables is
        a light lookup owned by the Academic module - kept as a TODO hook here
        so this module doesn't reach into Academic's internals directly."""
        user = await self.users.get_by_erp_user_id(erp_result.erp_user_id)
        if user is None:
            user = User(
                email=f"{erp_result.erp_user_id}@erp.local",  # ERP users may have no email on file
                user_type=self._map_erp_user_type(erp_result.user_type),
                auth_source="ERP",
                erp_user_id=erp_result.erp_user_id,
                status="ACTIVE",
            )
            self.users.add(user)
            await self.users.flush()
            role_name = {"ERP_STUDENT": "STUDENT"}.get(user.user_type, user.user_type)
            role = await self.roles.get_by_name(role_name)
            if role is not None:
                self.session.add(UserRole(user_id=user.id, role_id=role.id))
                await self.users.flush()
            await event_bus.publish(USER_REGISTERED, {"user_id": user.id, "source": "ERP"})
            logger.info("identity.erp_user_created", erp_user_id=erp_result.erp_user_id)
        return user

    @staticmethod
    def _map_erp_user_type(erp_user_type: str) -> str:
        mapping = {
            "STUDENT": "ERP_STUDENT",
            "TEACHER": "TEACHER",
            "SCHOOL_ADMIN": "SCHOOL_ADMIN",
            "ADMIN": "ADMIN",
        }
        return mapping.get(erp_user_type, "ERP_STUDENT")

    # ------------------------------------------------------------- Local ---
    async def register_external_student(self, payload: LocalRegisterRequest) -> User:
        existing = await self.users.get_by_email(payload.email)
        if existing is not None:
            raise ConflictError("An account with this email already exists")

        user = User(
            email=payload.email,
            phone=payload.phone,
            password_hash=hash_password(payload.password),
            user_type="EXTERNAL_STUDENT",
            auth_source="LOCAL",
            status="ACTIVE",
        )
        self.users.add(user)
        await self.users.flush()
        student_role = await self.roles.get_default_student_role()
        if student_role is not None:
            self.session.add(UserRole(user_id=user.id, role_id=student_role.id))
            await self.users.flush()
        await event_bus.publish(USER_REGISTERED, {"user_id": user.id, "source": "LOCAL"})
        logger.info("identity.external_student_registered", user_id=user.id)
        return user

    async def authenticate_local(self, payload: LocalLoginRequest) -> User:
        user = await self.users.get_by_email(payload.email)
        if user is None or user.password_hash is None:
            self.login_history.record(user_id=None, source="LOCAL", success=False)
            raise UnauthorizedError("Invalid email or password")

        if not verify_password(payload.password, user.password_hash):
            self.login_history.record(user_id=user.id, source="LOCAL", success=False)
            raise UnauthorizedError("Invalid email or password")

        if user.status != "ACTIVE":
            raise UnauthorizedError("Account is not active")

        self.login_history.record(user_id=user.id, source="LOCAL", success=True)
        await self.users.record_login(user.id)
        return user

    # ------------------------------------------------------------- Guest ---
    async def start_guest_session(self, payload: GuestStartRequest) -> tuple[User, str]:
        """Creates a real (but minimal) `users` row (Phase 1 §13). Returns
        (user, guest_pin). Guest PIN is a short human-typeable code used for
        exam-flow re-auth if the 4h token expires mid-exam (Phase 6 §6.3) -
        never used as the JWT secret."""
        guest_pin = "".join(secrets.choice(string.digits) for _ in range(6))
        guest_expires_at = utcnow() + timedelta(days=GUEST_RETENTION_DAYS)

        user = User(
            email=f"guest-{secrets.token_hex(8)}@guest.local",
            user_type="GUEST_STUDENT",
            auth_source="GUEST",
            status="ACTIVE",
            guest_expires_at=guest_expires_at,
            password_hash=hash_password(guest_pin),  # reuse password_hash slot for the PIN
        )
        self.users.add(user)
        await self.users.flush()

        # student_profiles(student_type=GUEST) row is created by StudentProfileService
        # (Phase 4 §6.3) - Identity only owns the `users` row itself.
        logger.info("identity.guest_session_started", user_id=user.id)
        return user, guest_pin

    # --------------------------------------------------------- Token I/O ---
    async def issue_tokens(self, user: User, *, is_guest: bool = False) -> IssuedTokens:
        role_names = await self.users.get_role_names(user.id)
        access_token, jti = create_access_token(
            public_id=str(user.public_id),
            user_type=user.user_type,
            auth_source=user.auth_source,
            roles=role_names,
            school_id=user.school_id,
            board_id=user.board_id,
            is_guest=is_guest,
        )

        refresh_token_value: str | None = None
        if not is_guest:
            # Guest users get NO refresh token (Phase 6 §6.3) - deliberately simple
            # since guest sessions are single-purpose and short.
            raw_token, token_hash = generate_refresh_token()
            refresh_token_value = raw_token
            refresh_row = RefreshToken(
                user_id=user.id,
                token_hash=token_hash,
                expires_at=utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS),
            )
            self.refresh_tokens.add(refresh_row)
            await self.refresh_tokens.flush()

        await event_bus.publish(USER_LOGGED_IN, {"user_id": user.id, "jti": jti})

        from app.core.security.jwt import GUEST_ACCESS_TOKEN_EXPIRE_HOURS

        expires_in = (
            GUEST_ACCESS_TOKEN_EXPIRE_HOURS * 3600
            if is_guest
            else settings.jwt.access_token_expire_minutes * 60
        )
        return IssuedTokens(
            access_token=access_token,
            refresh_token=refresh_token_value,
            expires_in_seconds=expires_in,
        )

    async def refresh(self, raw_refresh_token: str) -> IssuedTokens:
        """Rotates the refresh token: old one revoked, new one issued
        (Phase 6 §9)."""
        token_hash = hash_refresh_token(raw_refresh_token)
        existing = await self.refresh_tokens.get_by_token_hash(token_hash)
        if existing is None or not existing.is_valid():
            raise UnauthorizedError("Invalid or expired refresh token")

        # User.roles is mapped with lazy="selectin" (see models.py), so this
        # single get_by_id call already eager-loads roles - no extra query needed.
        user = await self.users.get_by_id(existing.user_id)
        if user is None:
            raise UnauthorizedError("User no longer exists")

        await self.refresh_tokens.revoke(existing)
        return await self.issue_tokens(user)

    async def logout(self, raw_refresh_token: str) -> None:
        token_hash = hash_refresh_token(raw_refresh_token)
        existing = await self.refresh_tokens.get_by_token_hash(token_hash)
        if existing is not None and existing.is_valid():
            await self.refresh_tokens.revoke(existing)
            await event_bus.publish(USER_LOGGED_OUT, {"user_id": existing.user_id})
