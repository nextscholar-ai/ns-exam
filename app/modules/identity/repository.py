"""
Identity module — repositories (Phase 6 §11).

`UserRepository`, `RefreshTokenRepository`, `RoleRepository`/`PermissionRepository`
(the latter two are read-mostly, seeded data). All DB access only - no business
logic (Phase 5 §7 layering rule).
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.cache import AsyncTTLCache
from app.core.db.base_model import utcnow
from app.core.db.base_repository import BaseRepository
from app.modules.identity.models import (
    LoginHistory,
    Permission,
    RefreshToken,
    Role,
    User,
    UserRole,
)

# Phase 8 §5.5 names RBAC role_permissions explicitly as one of the two
# datasets allowed a 60s in-process TTL cache (roles/permissions are seeded,
# not user-editable in v1 - Phase 6 §6.4).
_role_permission_cache = AsyncTTLCache(ttl_seconds=60)


class UserRepository(BaseRepository[User]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, User)

    async def get_by_email(self, email: str) -> User | None:
        stmt = (
            select(User)
            .where(User.email == email, User.is_deleted.is_(False))
            .options(selectinload(User.roles))
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_erp_user_id(self, erp_user_id: str) -> User | None:
        stmt = (
            select(User)
            .where(User.erp_user_id == erp_user_id, User.is_deleted.is_(False))
            .options(selectinload(User.roles))
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_public_id_with_roles(self, public_id) -> User | None:  # noqa: ANN001
        stmt = (
            select(User)
            .where(User.public_id == public_id, User.is_deleted.is_(False))
            .options(selectinload(User.roles))
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_role_names(self, user_id: int) -> list[str]:
        """Async-safe role-name lookup - never touches `User.roles` directly
        (that would lazy-load in an async session for freshly created users)."""
        stmt = (
            select(Role.name)
            .join(UserRole, UserRole.role_id == Role.id)
            .where(UserRole.user_id == user_id)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def record_login(self, user_id: int) -> None:
        user = await self.get_by_id(user_id)
        if user:
            user.last_login_at = utcnow()
            await self.flush()


class RoleRepository(BaseRepository[Role]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Role)

    async def get_by_name(self, name: str) -> Role | None:
        async def _load() -> Role | None:
            stmt = select(Role).where(Role.name == name, Role.is_deleted.is_(False))
            result = await self.session.execute(stmt)
            return result.scalar_one_or_none()

        return await _role_permission_cache.get_or_set(f"role:{name}", _load)

    async def get_default_student_role(self) -> Role | None:
        return await self.get_by_name("STUDENT")


class PermissionRepository(BaseRepository[Permission]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Permission)

    async def get_by_code(self, code: str) -> Permission | None:
        async def _load() -> Permission | None:
            stmt = select(Permission).where(
                Permission.code == code, Permission.is_deleted.is_(False)
            )
            result = await self.session.execute(stmt)
            return result.scalar_one_or_none()

        return await _role_permission_cache.get_or_set(f"permission:{code}", _load)


class RefreshTokenRepository(BaseRepository[RefreshToken]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, RefreshToken)

    async def get_by_token_hash(self, token_hash: str) -> RefreshToken | None:
        stmt = select(RefreshToken).where(
            RefreshToken.token_hash == token_hash, RefreshToken.is_deleted.is_(False)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def revoke(self, token: RefreshToken) -> None:
        token.revoked_at = utcnow()
        await self.flush()

    async def revoke_all_for_user(self, user_id: int) -> None:
        stmt = select(RefreshToken).where(
            RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None)
        )
        result = await self.session.execute(stmt)
        for token in result.scalars().all():
            token.revoked_at = utcnow()
        await self.flush()


class LoginHistoryRepository:
    """Append-only log - deliberately NOT a BaseRepository (no soft delete,
    no public_id semantics needed for an internal audit log)."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def record(
        self, *, user_id: int | None, source: str, success: bool, ip_address: str | None = None
    ) -> LoginHistory:
        entry = LoginHistory(user_id=user_id, source=source, success=success, ip_address=ip_address)
        self.session.add(entry)
        return entry
