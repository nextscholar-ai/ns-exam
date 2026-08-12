"""
Phase 8 §16 exit-criteria tests, run against a real database (SQLite
in-memory, see `conftest.py`'s `sqlite_session` fixture) rather than mocks:

  1. Soft-delete filter: create -> soft-delete -> confirm `get_by_id` returns
     None -> confirm `include_deleted=True` returns it.
  2. School-scoping: two schools' data seeded, confirm a school-scoped user's
     `list()` never returns the other school's rows, and `get_by_id` for a
     row outside their school returns None (IDOR defense, Phase 8 §9).
"""
import pytest

from app.core.db.base_repository import BaseRepository
from app.core.security.rbac import CurrentUser
from app.modules.academic.models import Board, Class, School


def _teacher(school_id: int) -> CurrentUser:
    return CurrentUser(
        public_id="teacher-1",
        user_type="TEACHER",
        auth_source="ERP",
        roles=["TEACHER"],
        school_id=school_id,
        board_id=None,
        jti="test-jti",
    )


def _super_admin() -> CurrentUser:
    return CurrentUser(
        public_id="admin-1",
        user_type="ADMIN",
        auth_source="ERP",
        roles=["SUPER_ADMIN"],
        school_id=None,
        board_id=None,
        jti="test-jti",
    )


async def _seed_board_and_schools(session) -> tuple[Board, School, School]:
    board_repo = BaseRepository(session, Board)
    board = await board_repo.create({"erp_id": "board-1", "name": "CBSE"})

    school_repo = BaseRepository(session, School)
    school_a = await school_repo.create({"erp_id": "school-a", "board_id": board.id, "name": "School A"})
    school_b = await school_repo.create({"erp_id": "school-b", "board_id": board.id, "name": "School B"})
    await session.flush()
    return board, school_a, school_b


@pytest.mark.asyncio
async def test_soft_delete_hides_row_but_include_deleted_reveals_it(sqlite_session):
    board_repo = BaseRepository(sqlite_session, Board)
    board = await board_repo.create({"erp_id": "board-soft-delete", "name": "ICSE"})
    await sqlite_session.flush()

    found = await board_repo.get_by_id(board.id)
    assert found is not None

    await board_repo.soft_delete(board.id, deleted_by=1)

    hidden = await board_repo.get_by_id(board.id)
    assert hidden is None

    revealed = await board_repo.get_by_id(board.id, include_deleted=True)
    assert revealed is not None
    assert revealed.is_deleted is True
    assert revealed.deleted_by == 1


@pytest.mark.asyncio
async def test_list_excludes_soft_deleted_rows_by_default(sqlite_session):
    board_repo = BaseRepository(sqlite_session, Board)
    keep = await board_repo.create({"erp_id": "board-keep", "name": "Keep Me"})
    gone = await board_repo.create({"erp_id": "board-gone", "name": "Delete Me"})
    await sqlite_session.flush()
    await board_repo.soft_delete(gone.id, deleted_by=1)

    rows, total = await board_repo.list()
    names = {r.name for r in rows}
    assert "Keep Me" in names
    assert "Delete Me" not in names
    assert total == 1


@pytest.mark.asyncio
async def test_school_scoping_hides_other_schools_rows(sqlite_session):
    _, school_a, school_b = await _seed_board_and_schools(sqlite_session)

    class_repo = BaseRepository(sqlite_session, Class)
    class_a = await class_repo.create(
        {"erp_id": "class-a", "school_id": school_a.id, "name": "Class 10-A"}
    )
    class_b = await class_repo.create(
        {"erp_id": "class-b", "school_id": school_b.id, "name": "Class 10-B"}
    )
    await sqlite_session.flush()

    teacher_at_school_a = _teacher(school_a.id)

    rows, total = await class_repo.list(current_user=teacher_at_school_a)
    assert total == 1
    assert rows[0].id == class_a.id
    assert all(r.school_id == school_a.id for r in rows)

    # IDOR defense: fetching the OTHER school's row by id returns None, not
    # a 403 - existence is never leaked (Phase 8 §9).
    leaked = await class_repo.get_by_id(class_b.id, current_user=teacher_at_school_a)
    assert leaked is None

    # SUPER_ADMIN bypasses scoping entirely.
    admin_rows, admin_total = await class_repo.list(current_user=_super_admin())
    assert admin_total == 2


@pytest.mark.asyncio
async def test_hard_delete_actually_removes_the_row(sqlite_session):
    board_repo = BaseRepository(sqlite_session, Board)
    board = await board_repo.create({"erp_id": "board-hard-delete", "name": "Temp Board"})
    await sqlite_session.flush()

    await board_repo.hard_delete(board.id)
    await sqlite_session.flush()

    gone = await board_repo.get_by_id(board.id, include_deleted=True)
    assert gone is None


@pytest.mark.asyncio
async def test_update_mutates_and_returns_the_instance(sqlite_session):
    board_repo = BaseRepository(sqlite_session, Board)
    board = await board_repo.create({"erp_id": "board-update", "name": "Old Name"})
    await sqlite_session.flush()

    updated = await board_repo.update(board.id, {"name": "New Name"})
    assert updated.name == "New Name"

    refetched = await board_repo.get_by_id(board.id)
    assert refetched.name == "New Name"


@pytest.mark.asyncio
async def test_invalid_filter_key_raises_validation_error(sqlite_session):
    from app.core.exceptions import ValidationDomainError

    board_repo = BaseRepository(sqlite_session, Board)
    with pytest.raises(ValidationDomainError):
        await board_repo.list(filters={"not_a_real_column": "x"})


@pytest.mark.asyncio
async def test_get_or_raise_and_restore(sqlite_session):
    from app.core.exceptions import NotFoundError

    board_repo = BaseRepository(sqlite_session, Board)
    board = await board_repo.create({"erp_id": "board-raise", "name": "Raise Board"})
    await sqlite_session.flush()

    found = await board_repo.get_or_raise(board.id)
    assert found.name == "Raise Board"

    await board_repo.soft_delete(board.id, deleted_by=1)
    with pytest.raises(NotFoundError):
        await board_repo.get_or_raise(board.id)

    restored = await board_repo.restore(board.id)
    assert restored.is_deleted is False


@pytest.mark.asyncio
async def test_bulk_operations_and_paginate(sqlite_session):
    board_repo = BaseRepository(sqlite_session, Board)
    created = await board_repo.bulk_create([
        {"erp_id": f"board-bulk-{i}", "name": f"Board {i}"} for i in range(5)
    ])
    assert len(created) == 5

    res = await board_repo.paginate(page=1, page_size=2)
    assert res["page"] == 1
    assert res["page_size"] == 2
    assert len(res["items"]) == 2

    updated_count = await board_repo.bulk_update([
        {"id": created[0].id, "name": "Updated Board 0"},
        {"id": created[1].id, "name": "Updated Board 1"},
    ])
    assert updated_count == 2

    search_res = await board_repo.search(term="Updated", fields=["name"])
    assert len(search_res) == 2


@pytest.mark.asyncio
async def test_first_or_create_and_upsert(sqlite_session):
    board_repo = BaseRepository(sqlite_session, Board)
    obj, is_new = await board_repo.first_or_create(defaults={"name": "New Board"}, erp_id="unique-erp-1")
    assert is_new is True
    assert obj.name == "New Board"

    obj_again, is_new_again = await board_repo.first_or_create(defaults={"name": "New Board"}, erp_id="unique-erp-1")
    assert is_new_again is False

    upserted = await board_repo.upsert(match_fields={"erp_id": "unique-erp-1"}, data={"name": "Upserted Name"})
    assert upserted.id == obj.id
    assert upserted.name == "Upserted Name"

