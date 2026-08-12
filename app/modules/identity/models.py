"""
Identity module — ORM models (Phase 4 §6.1).

Aggregate root: `User`. Also owns `Company` (single-tenant root, Phase 3 §5),
RBAC tables (`Role`, `Permission`, association tables), `RefreshToken`, and the
append-only `LoginHistory` log.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db.base_model import Base, BaseMixin, BigIntPk, utcnow


class Company(BaseMixin, Base):
    """Single-tenant root. Exactly one row in v1 (Phase 1 §13). Exists now so a
    future multi-tenant migration only needs to add `company_id` FKs, not
    invent this table (Phase 4 §23)."""

    __tablename__ = "companies"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class User(BaseMixin, Base):
    """Aggregate root of the Identity bounded context."""

    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # SUPER_ADMIN | ADMIN | SCHOOL_ADMIN | TEACHER | ERP_STUDENT | EXTERNAL_STUDENT | GUEST_STUDENT
    user_type: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    # ERP | LOCAL | GUEST
    auth_source: Mapped[str] = mapped_column(String(20), nullable=False)

    erp_user_id: Mapped[str | None] = mapped_column(
        String(100), unique=True, nullable=True, index=True
    )

    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE")

    school_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("schools.id"), nullable=True, index=True
    )
    board_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("boards.id"), nullable=True
    )

    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    guest_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )

    roles: Mapped[list["Role"]] = relationship(
        secondary="user_roles", back_populates="users", lazy="selectin"
    )
    refresh_tokens: Mapped[list["RefreshToken"]] = relationship(
        back_populates="user", lazy="raise", foreign_keys="RefreshToken.user_id"
    )


class Role(BaseMixin, Base):
    __tablename__ = "roles"

    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)

    users: Mapped[list["User"]] = relationship(
        secondary="user_roles", back_populates="roles", lazy="raise"
    )
    permissions: Mapped[list["Permission"]] = relationship(
        secondary="role_permissions", back_populates="roles", lazy="selectin"
    )


class Permission(BaseMixin, Base):
    __tablename__ = "permissions"

    code: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)

    roles: Mapped[list["Role"]] = relationship(
        secondary="role_permissions", back_populates="permissions", lazy="raise"
    )


class RolePermission(Base):
    """`role_id` + `permission_id` composite PK — pure association table, no
    BaseMixin (it has no independent identity beyond the pair)."""

    __tablename__ = "role_permissions"

    role_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("roles.id"), primary_key=True)
    permission_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("permissions.id"), primary_key=True
    )


class UserRole(Base):
    """`user_id` + `role_id` composite PK — a user can hold more than one role
    (e.g. Teacher + School Admin, Phase 4 §6.1)."""

    __tablename__ = "user_roles"

    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), primary_key=True)
    role_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("roles.id"), primary_key=True)


class RefreshToken(BaseMixin, Base):
    __tablename__ = "refresh_tokens"
    __table_args__ = (UniqueConstraint("token_hash", name="uq_refresh_tokens_token_hash"),)

    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    device_info: Mapped[str | None] = mapped_column(String(255), nullable=True)

    user: Mapped["User"] = relationship(
        back_populates="refresh_tokens", lazy="raise", foreign_keys="RefreshToken.user_id"
    )

    def is_valid(self) -> bool:
        return self.revoked_at is None and self.expires_at > utcnow()


class LoginHistory(Base):
    """Append-only log table — the one documented BaseMixin exception
    (Phase 3 §9): keeps a timestamp via `login_at`, no soft delete."""

    __tablename__ = "login_history"

    id: Mapped[int] = mapped_column(BigIntPk(), primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id"), nullable=True, index=True
    )
    login_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    source: Mapped[str] = mapped_column(String(20), nullable=False)  # ERP | LOCAL | GUEST
    success: Mapped[bool] = mapped_column(Boolean, nullable=False)
