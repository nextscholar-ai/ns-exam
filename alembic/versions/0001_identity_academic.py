"""Phase 4/6 — Identity + Academic Snapshot + Student/Teacher schema

Revision ID: 0001_identity_academic
Revises:
Create Date: 2026-08-08

Matches Phase 4 §6 table designs exactly. Written by hand against the ORM
models since this sandbox has no live Postgres to run --autogenerate against;
regenerate with `alembic revision --autogenerate` after a real DB diff if you
change any model before applying this.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision: str = "0001_identity_academic"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _base_mixin_columns() -> list[sa.Column]:
    return [
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("public_id", UUID(as_uuid=True), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    ]


def _snapshot_extra_columns() -> list[sa.Column]:
    return [
        sa.Column("erp_id", sa.String(64), nullable=False, unique=True),
        sa.Column("sync_status", sa.String(20), nullable=False, server_default="SYNCED"),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=False),
    ]


def upgrade() -> None:
    # ---- companies (single-tenant root) ----
    op.create_table(
        "companies",
        *_base_mixin_columns(),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )

    # ---- boards (SnapshotMixin) ----
    op.create_table(
        "boards",
        *_base_mixin_columns(),
        *_snapshot_extra_columns(),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("code", sa.String(50), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="ACTIVE"),
    )

    # ---- schools ----
    op.create_table(
        "schools",
        *_base_mixin_columns(),
        *_snapshot_extra_columns(),
        sa.Column("board_id", sa.BigInteger(), sa.ForeignKey("boards.id"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="ACTIVE"),
    )
    op.create_index("ix_schools_board_id", "schools", ["board_id"])

    # ---- users ----
    op.create_table(
        "users",
        *_base_mixin_columns(),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("phone", sa.String(20), nullable=True),
        sa.Column("password_hash", sa.String(255), nullable=True),
        sa.Column("user_type", sa.String(30), nullable=False),
        sa.Column("auth_source", sa.String(20), nullable=False),
        sa.Column("erp_user_id", sa.String(100), nullable=True, unique=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="ACTIVE"),
        sa.Column("school_id", sa.BigInteger(), sa.ForeignKey("schools.id"), nullable=True),
        sa.Column("board_id", sa.BigInteger(), sa.ForeignKey("boards.id"), nullable=True),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("guest_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by", sa.BigInteger(), sa.ForeignKey("users.id"), nullable=True),
    )
    op.create_index("ix_users_email", "users", ["email"])
    op.create_index("ix_users_erp_user_id", "users", ["erp_user_id"])
    op.create_index("ix_users_school_id", "users", ["school_id"])
    op.create_index("ix_users_user_type_status", "users", ["user_type", "status"])
    op.create_index(
        "ix_users_guest_expires_at",
        "users",
        ["guest_expires_at"],
        postgresql_where=sa.text("user_type = 'GUEST_STUDENT'"),
    )

    # now that `users` exists, add its deferred deleted_by FKs on earlier tables
    for table in ("companies", "boards", "schools"):
        op.add_column(
            table, sa.Column("deleted_by", sa.BigInteger(), sa.ForeignKey("users.id"), nullable=True)
        )

    # ---- roles / permissions / associations ----
    op.create_table(
        "roles",
        *_base_mixin_columns(),
        sa.Column("deleted_by", sa.BigInteger(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("name", sa.String(50), nullable=False, unique=True),
        sa.Column("description", sa.String(255), nullable=True),
    )
    op.create_table(
        "permissions",
        *_base_mixin_columns(),
        sa.Column("deleted_by", sa.BigInteger(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("code", sa.String(100), nullable=False, unique=True),
        sa.Column("description", sa.String(255), nullable=True),
    )
    op.create_table(
        "role_permissions",
        sa.Column("role_id", sa.BigInteger(), sa.ForeignKey("roles.id"), primary_key=True),
        sa.Column(
            "permission_id", sa.BigInteger(), sa.ForeignKey("permissions.id"), primary_key=True
        ),
    )
    op.create_table(
        "user_roles",
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("role_id", sa.BigInteger(), sa.ForeignKey("roles.id"), primary_key=True),
    )

    # ---- refresh_tokens ----
    op.create_table(
        "refresh_tokens",
        *_base_mixin_columns(),
        sa.Column("deleted_by", sa.BigInteger(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("token_hash", sa.String(255), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("device_info", sa.String(255), nullable=True),
    )
    op.create_index("ix_refresh_tokens_user_id", "refresh_tokens", ["user_id"])

    # ---- login_history (append-only, no soft delete) ----
    op.create_table(
        "login_history",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("login_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("source", sa.String(20), nullable=False),
        sa.Column("success", sa.Boolean(), nullable=False),
    )
    op.create_index("ix_login_history_user_id", "login_history", ["user_id"])

    # ---- academic_sessions / classes / subjects / chapters / units / topics ----
    op.create_table(
        "academic_sessions",
        *_base_mixin_columns(),
        sa.Column("deleted_by", sa.BigInteger(), sa.ForeignKey("users.id"), nullable=True),
        *_snapshot_extra_columns(),
        sa.Column("school_id", sa.BigInteger(), sa.ForeignKey("schools.id"), nullable=False),
        sa.Column("name", sa.String(50), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index("ix_academic_sessions_school_id", "academic_sessions", ["school_id"])

    op.create_table(
        "classes",
        *_base_mixin_columns(),
        sa.Column("deleted_by", sa.BigInteger(), sa.ForeignKey("users.id"), nullable=True),
        *_snapshot_extra_columns(),
        sa.Column("school_id", sa.BigInteger(), sa.ForeignKey("schools.id"), nullable=False),
        sa.Column("name", sa.String(50), nullable=False),
    )
    op.create_index("ix_classes_school_id", "classes", ["school_id"])

    op.create_table(
        "subjects",
        *_base_mixin_columns(),
        sa.Column("deleted_by", sa.BigInteger(), sa.ForeignKey("users.id"), nullable=True),
        *_snapshot_extra_columns(),
        sa.Column("board_id", sa.BigInteger(), sa.ForeignKey("boards.id"), nullable=False),
        sa.Column("class_id", sa.BigInteger(), sa.ForeignKey("classes.id"), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
    )
    op.create_index("ix_subjects_board_class", "subjects", ["board_id", "class_id"])

    op.create_table(
        "chapters",
        *_base_mixin_columns(),
        sa.Column("deleted_by", sa.BigInteger(), sa.ForeignKey("users.id"), nullable=True),
        *_snapshot_extra_columns(),
        sa.Column("subject_id", sa.BigInteger(), sa.ForeignKey("subjects.id"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("sequence", sa.SmallInteger(), nullable=True),
    )
    op.create_index("ix_chapters_subject_id", "chapters", ["subject_id"])

    op.create_table(
        "units",
        *_base_mixin_columns(),
        sa.Column("deleted_by", sa.BigInteger(), sa.ForeignKey("users.id"), nullable=True),
        *_snapshot_extra_columns(),
        sa.Column("chapter_id", sa.BigInteger(), sa.ForeignKey("chapters.id"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
    )
    op.create_index("ix_units_chapter_id", "units", ["chapter_id"])

    op.create_table(
        "topics",
        *_base_mixin_columns(),
        sa.Column("deleted_by", sa.BigInteger(), sa.ForeignKey("users.id"), nullable=True),
        *_snapshot_extra_columns(),
        sa.Column("unit_id", sa.BigInteger(), sa.ForeignKey("units.id"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
    )
    op.create_index("ix_topics_unit_id", "topics", ["unit_id"])

    # ---- student_profiles ----
    op.create_table(
        "student_profiles",
        *_base_mixin_columns(),
        sa.Column("deleted_by", sa.BigInteger(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("student_type", sa.String(20), nullable=False),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("erp_student_id", sa.String(100), nullable=True, unique=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("roll_number", sa.String(50), nullable=True),
        sa.Column("school_id", sa.BigInteger(), sa.ForeignKey("schools.id"), nullable=True),
        sa.Column("board_id", sa.BigInteger(), sa.ForeignKey("boards.id"), nullable=True),
        sa.Column("class_id", sa.BigInteger(), sa.ForeignKey("classes.id"), nullable=True),
        sa.Column(
            "academic_session_id",
            sa.BigInteger(),
            sa.ForeignKey("academic_sessions.id"),
            nullable=True,
        ),
        sa.Column("status", sa.String(20), nullable=False, server_default="ACTIVE"),
        sa.Column("sync_status", sa.String(20), nullable=False, server_default="SYNCED"),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_student_profiles_erp_student_id", "student_profiles", ["erp_student_id"])
    op.create_index(
        "ix_student_profiles_school_class", "student_profiles", ["school_id", "class_id"]
    )
    op.create_index("ix_student_profiles_student_type", "student_profiles", ["student_type"])
    op.create_index("ix_student_profiles_user_id", "student_profiles", ["user_id"])

    # ---- teacher_profiles / teacher_subject_map ----
    op.create_table(
        "teacher_profiles",
        *_base_mixin_columns(),
        sa.Column("deleted_by", sa.BigInteger(), sa.ForeignKey("users.id"), nullable=True),
        *_snapshot_extra_columns(),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("erp_teacher_id", sa.String(100), nullable=False, unique=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("school_id", sa.BigInteger(), sa.ForeignKey("schools.id"), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="ACTIVE"),
    )
    op.create_index("ix_teacher_profiles_user_id", "teacher_profiles", ["user_id"])
    op.create_index("ix_teacher_profiles_school_id", "teacher_profiles", ["school_id"])

    op.create_table(
        "teacher_subject_map",
        sa.Column(
            "teacher_id", sa.BigInteger(), sa.ForeignKey("teacher_profiles.id"), primary_key=True
        ),
        sa.Column("subject_id", sa.BigInteger(), sa.ForeignKey("subjects.id"), primary_key=True),
    )


def downgrade() -> None:
    op.drop_table("teacher_subject_map")
    op.drop_table("teacher_profiles")
    op.drop_table("student_profiles")
    op.drop_table("topics")
    op.drop_table("units")
    op.drop_table("chapters")
    op.drop_table("subjects")
    op.drop_table("classes")
    op.drop_table("academic_sessions")
    op.drop_table("login_history")
    op.drop_table("refresh_tokens")
    op.drop_table("user_roles")
    op.drop_table("role_permissions")
    op.drop_table("permissions")
    op.drop_table("roles")
    op.drop_column("schools", "deleted_by")
    op.drop_column("boards", "deleted_by")
    op.drop_column("companies", "deleted_by")
    op.drop_table("users")
    op.drop_table("schools")
    op.drop_table("boards")
    op.drop_table("companies")
