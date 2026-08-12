"""
Phase 10 Question Bank module unit & integration tests.

Tests:
  1. Creation of Objective, Subjective, and FillBlank questions.
  2. Duplicate detection (exact and fuzzy matching).
  3. Polymorphic version snapshot creation and history lookup.
  4. Question search filter chain.
  5. Status lifecycle transitions.
"""
import pytest

from app.core.security.rbac import CurrentUser
from app.modules.academic.models import Board, Chapter, Class, Subject
from app.modules.question_bank.domain.duplicate_detection import (
    calculate_similarity,
    check_duplicate_candidate,
)
from app.modules.question_bank.schemas import (
    FillBlankQuestionCreate,
    ObjectiveQuestionCreate,
    OptionSchema,
    QuestionSearchFilters,
    SubjectiveQuestionCreate,
)
from app.modules.question_bank.service import QuestionBankService


def _teacher(board_id: int = 1) -> CurrentUser:
    return CurrentUser(
        public_id="teacher-1",
        user_type="TEACHER",
        auth_source="ERP",
        roles=["TEACHER"],
        school_id=10,
        board_id=board_id,
        jti="test-jti",
    )


async def _seed_academic_hierarchy(session) -> tuple[Board, Class, Subject, Chapter]:
    from app.core.db.base_repository import BaseRepository
    from app.modules.academic.models import School

    board_repo = BaseRepository(session, Board)
    board = await board_repo.create(
        {"erp_id": "board-qb-1", "name": "CBSE"}
    )

    school_repo = BaseRepository(session, School)
    school = await school_repo.create(
        {"erp_id": "school-qb-1", "name": "Test School", "board_id": board.id}
    )

    class_repo = BaseRepository(session, Class)
    cls = await class_repo.create(
        {"erp_id": "class-qb-1", "name": "Class 10", "school_id": school.id}
    )

    subj_repo = BaseRepository(session, Subject)
    subj = await subj_repo.create(
        {
            "erp_id": "subj-qb-1",
            "name": "Science",
            "board_id": board.id,
            "class_id": cls.id,
        }
    )

    chap_repo = BaseRepository(session, Chapter)
    chap = await chap_repo.create(
        {
            "erp_id": "chap-qb-1",
            "subject_id": subj.id,
            "name": "Chemical Reactions",
            "sequence": 1,
        }
    )

    await session.flush()
    return board, cls, subj, chap


@pytest.mark.asyncio
async def test_create_objective_subjective_and_fill_blank_questions(sqlite_session):
    board, cls, subj, chap = await _seed_academic_hierarchy(sqlite_session)
    service = QuestionBankService(sqlite_session)
    teacher = _teacher(board.id)

    # 1. Objective Question
    obj_payload = ObjectiveQuestionCreate(
        board_id=board.id,
        class_id=cls.id,
        subject_id=subj.id,
        primary_chapter_id=chap.id,
        question_text="What is the chemical formula of water?",
        options=[
            OptionSchema(label="A", text="H2O"),
            OptionSchema(label="B", text="CO2"),
            OptionSchema(label="C", text="NaCl"),
            OptionSchema(label="D", text="O2"),
        ],
        correct_option="A",
        difficulty="EASY",
        bloom_level="REMEMBER",
        marks=1.0,
    )
    obj_res = await service.create_objective_question(obj_payload, current_user=teacher)
    assert obj_res["question_type"] == "OBJECTIVE"
    assert obj_res["correct_option"] == "A"
    assert obj_res["status"] == "DRAFT"

    # 2. Subjective Question
    subj_payload = SubjectiveQuestionCreate(
        board_id=board.id,
        class_id=cls.id,
        subject_id=subj.id,
        primary_chapter_id=chap.id,
        question_text="Explain Photosynthesis in detail.",
        model_answer_text="Photosynthesis is the process by which green plants convert light energy into chemical energy.",
        max_marks=5.0,
        expected_key_points=["Chlorophyll", "Sunlight", "Glucose"],
        difficulty="MEDIUM",
        bloom_level="UNDERSTAND",
    )
    subj_res = await service.create_subjective_question(subj_payload, current_user=teacher)
    assert subj_res["question_type"] == "SUBJECTIVE"
    assert subj_res["marks"] == 5.0

    # 3. Fill Blank Question
    fill_payload = FillBlankQuestionCreate(
        board_id=board.id,
        class_id=cls.id,
        subject_id=subj.id,
        primary_chapter_id=chap.id,
        question_text_with_blanks="The capital of France is ___.",
        correct_answers=["Paris"],
        marks=1.0,
    )
    fill_res = await service.create_fill_blank_question(fill_payload, current_user=teacher)
    assert fill_res["question_type"] == "FILL_BLANK"


@pytest.mark.asyncio
async def test_duplicate_detection_logic():
    cand_1 = {"id": 1, "public_id": "p1", "question_text": "What is the capital of France?"}

    res_exact = check_duplicate_candidate("What is the capital of France?", [cand_1], threshold=90.0)
    assert res_exact.is_duplicate is True
    assert res_exact.match_type == "EXACT"

    res_fuzzy = check_duplicate_candidate("What is capital of France?", [cand_1], threshold=80.0)
    assert res_fuzzy.is_duplicate is True

    res_none = check_duplicate_candidate("How many planets are in solar system?", [cand_1], threshold=90.0)
    assert res_none.is_duplicate is False


@pytest.mark.asyncio
async def test_versioning_and_status_lifecycle(sqlite_session):
    board, cls, subj, chap = await _seed_academic_hierarchy(sqlite_session)
    service = QuestionBankService(sqlite_session)
    teacher = _teacher(board.id)

    obj_payload = ObjectiveQuestionCreate(
        board_id=board.id,
        class_id=cls.id,
        subject_id=subj.id,
        primary_chapter_id=chap.id,
        question_text="Sample Question text",
        options=[OptionSchema(label="A", text="Opt 1"), OptionSchema(label="B", text="Opt 2")],
        correct_option="A",
    )
    q = await service.create_objective_question(obj_payload, current_user=teacher)
    pub_id = q["public_id"]

    # Change status to ACTIVE
    activated = await service.change_status(pub_id, "ACTIVE", current_user=teacher)
    assert activated["status"] == "ACTIVE"

    # Create new version
    ver_res = await service.create_version(
        public_id=pub_id,
        change_reason="Corrected typo in text",
        updated_data={"question_text": "Sample Question text corrected"},
        current_user=teacher,
    )
    assert ver_res["version_no"] == 2

    history = await service.get_version_history(pub_id, current_user=teacher)
    assert len(history) == 2
    assert history[0]["version_no"] == 2


@pytest.mark.asyncio
async def test_search_questions_filter(sqlite_session):
    board, cls, subj, chap = await _seed_academic_hierarchy(sqlite_session)
    service = QuestionBankService(sqlite_session)
    teacher = _teacher(board.id)

    obj_payload = ObjectiveQuestionCreate(
        board_id=board.id,
        class_id=cls.id,
        subject_id=subj.id,
        primary_chapter_id=chap.id,
        question_text="Search target objective question text",
        options=[OptionSchema(label="A", text="Opt 1"), OptionSchema(label="B", text="Opt 2")],
        correct_option="A",
    )
    q = await service.create_objective_question(obj_payload, current_user=teacher)
    await service.change_status(q["public_id"], "ACTIVE", current_user=teacher)

    filters = QuestionSearchFilters(board_id=board.id, subject_id=subj.id, status="ACTIVE")
    items, total = await service.search_questions(filters, current_user=teacher)
    assert total >= 1
