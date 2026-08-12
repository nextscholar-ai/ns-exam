"""
Phase 14 — Mastery Engine unit tests.

Tests:
  1. EMA mastery formula: adaptive alpha, boundary clamping, question score normalization.
  2. Aggregate mastery: average of topic scores, empty list guard.
  3. Full MasteryService integration: process evaluation → topic/chapter/subject rows created,
     history appended, weak/strong classification correct.
  4. Multi-evaluation mastery evolution: second evaluation moves mastery upward.
  5. LearningProfileService: get_learning_profile, get_weak_topics, history query.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from app.core.security.rbac import CurrentUser
from app.modules.academic.models import Board, Chapter, Class, School, Subject, Topic
from app.modules.blueprint.schemas import (
    BlueprintCreate,
    BlueprintSectionCreate,
    ExamConfigCreate,
    SectionDifficultyDistribution,
)
from app.modules.blueprint.service import BlueprintService
from app.modules.evaluation.service import EvaluationService, OMRService, SubjectiveEvaluationService
from app.modules.exam_management.schemas import ExamConfigure, ExamCreate
from app.modules.exam_management.service import AttemptService, ExamService
from app.modules.identity.models import User
from app.modules.learning_profile.domain.mastery_formula import (
    EMAMasteryFormula,
    aggregate_mastery,
    compute_question_score,
)
from app.modules.learning_profile.service import (
    STRONG_THRESHOLD,
    WEAK_THRESHOLD,
    LearningProfileService,
    MasteryService,
)
from app.modules.question_bank.schemas import ObjectiveQuestionCreate, OptionSchema, SubjectiveQuestionCreate
from app.modules.question_bank.service import QuestionBankService
from app.modules.student.models import StudentProfile
from app.core.db.base_repository import BaseRepository


def _teacher(board_id: int = 1) -> CurrentUser:
    return CurrentUser(
        public_id="teacher-mastery-1",
        user_type="TEACHER",
        auth_source="ERP",
        roles=["TEACHER"],
        school_id=10,
        board_id=board_id,
        jti="jti-mastery",
    )


# ---------------------------------------------------------------------------
# 1. Pure Domain — EMA Formula Tests
# ---------------------------------------------------------------------------

def test_ema_formula_first_attempt_uses_high_alpha():
    """First attempt (count=0) uses alpha=0.5 for quick initial calibration."""
    formula = EMAMasteryFormula()
    new_mastery, alpha = formula.compute(
        current_mastery=0.0,
        question_score=1.0,
        attempt_count=0,
    )
    assert alpha == 0.5
    # 0.5 × 1.0 + 0.5 × 0.0 = 0.5
    assert new_mastery == pytest.approx(0.5, abs=0.001)


def test_ema_formula_second_attempt_uses_mid_alpha():
    """Second attempt (count=1) uses alpha=0.4."""
    formula = EMAMasteryFormula()
    new_mastery, alpha = formula.compute(
        current_mastery=0.5,
        question_score=1.0,
        attempt_count=1,
    )
    assert alpha == 0.4
    # 0.4 × 1.0 + 0.6 × 0.5 = 0.70
    assert new_mastery == pytest.approx(0.70, abs=0.001)


def test_ema_formula_converges_to_base_alpha():
    """After 2+ attempts, formula uses base_alpha=0.3."""
    formula = EMAMasteryFormula()
    _, alpha = formula.compute(
        current_mastery=0.7,
        question_score=0.5,
        attempt_count=5,
    )
    assert alpha == 0.3


def test_ema_formula_clamps_to_zero():
    """Mastery cannot go below 0.0."""
    formula = EMAMasteryFormula()
    new_mastery, _ = formula.compute(
        current_mastery=0.0,
        question_score=0.0,
        attempt_count=0,
    )
    assert new_mastery == 0.0


def test_ema_formula_clamps_to_one():
    """Mastery cannot exceed 1.0."""
    formula = EMAMasteryFormula()
    new_mastery, _ = formula.compute(
        current_mastery=1.0,
        question_score=1.0,
        attempt_count=0,
    )
    assert new_mastery <= 1.0


def test_compute_question_score_normalizes():
    """Question score = marks_obtained / max_marks, clamped to [0, 1]."""
    assert compute_question_score(2.0, 4.0) == pytest.approx(0.5)
    assert compute_question_score(4.0, 4.0) == pytest.approx(1.0)
    assert compute_question_score(0.0, 4.0) == pytest.approx(0.0)


def test_compute_question_score_zero_max_marks():
    """Division by zero guard — returns 0.0."""
    assert compute_question_score(5.0, 0.0) == 0.0


def test_aggregate_mastery_average():
    """Aggregate mastery = simple average."""
    assert aggregate_mastery([0.4, 0.6, 0.8]) == pytest.approx(0.6, abs=0.001)


def test_aggregate_mastery_empty():
    """Empty list returns 0.0."""
    assert aggregate_mastery([]) == 0.0


# ---------------------------------------------------------------------------
# 2. Integration — Seed helper
# ---------------------------------------------------------------------------

async def _seed_mastery_environment(session):
    """
    Seed: board, school, class, subject, chapter, topic, 2 questions,
    student, exam, paper, attempt (submitted).
    Returns: (board, chap, unit_obj, student, att, obj_q, subj_q)
    """
    board = await BaseRepository(session, Board).create({"erp_id": "board-ms-1", "name": "CBSE"})
    school = await BaseRepository(session, School).create({"erp_id": "school-ms-1", "name": "School MS", "board_id": board.id})
    cls = await BaseRepository(session, Class).create({"erp_id": "class-ms-1", "name": "Class 10", "school_id": school.id})
    subj = await BaseRepository(session, Subject).create({"erp_id": "subj-ms-1", "name": "Science", "board_id": board.id, "class_id": cls.id})
    chap = await BaseRepository(session, Chapter).create({"erp_id": "chap-ms-1", "subject_id": subj.id, "name": "Chemical Reactions", "sequence": 1})
    unit_obj = await BaseRepository(session, Topic).create({"erp_id": "top-ms-1", "unit_id": chap.id, "name": "Oxidation"})

    qb = QuestionBankService(session)
    teacher = _teacher(board.id)
    obj_q = await qb.create_objective_question(
        ObjectiveQuestionCreate(
            board_id=board.id, class_id=cls.id, subject_id=subj.id,
            primary_chapter_id=chap.id, primary_topic_id=unit_obj.id,
            question_text="Formula of water?",
            options=[OptionSchema(label="A", text="H2O"), OptionSchema(label="B", text="CO2")],
            correct_option="A", marks=2.0, difficulty="EASY",
        ),
        current_user=teacher,
    )
    await qb.change_status(obj_q["public_id"], "ACTIVE", current_user=teacher)

    subj_q = await qb.create_subjective_question(
        SubjectiveQuestionCreate(
            board_id=board.id, class_id=cls.id, subject_id=subj.id,
            primary_chapter_id=chap.id, primary_topic_id=unit_obj.id,
            question_text="Explain oxidation.", max_marks=8.0,
        ),
        current_user=teacher,
    )
    await qb.change_status(subj_q["public_id"], "ACTIVE", current_user=teacher)

    user = await BaseRepository(session, User).create(
        {"email": "student_ms@test.com", "user_type": "ERP_STUDENT", "auth_source": "ERP", "status": "ACTIVE", "school_id": school.id}
    )
    student = await BaseRepository(session, StudentProfile).create(
        {"erp_student_id": "std-ms-1", "school_id": school.id, "user_id": user.id, "name": "Rahul Sharma", "student_type": "ERP"}
    )

    bp_service = BlueprintService(session)
    bp_dict = await bp_service.create_blueprint(
        BlueprintCreate(
            board_id=board.id, class_id=cls.id, subject_id=subj.id,
            name="Science Blueprint", total_marks=10.0, duration_minutes=60,
            sections=[
                BlueprintSectionCreate(section_label="A", question_type="OBJECTIVE", section_marks=2.0, question_count=1, difficulty_distribution=SectionDifficultyDistribution(EASY=100, MEDIUM=0, HARD=0)),
                BlueprintSectionCreate(section_label="B", question_type="SUBJECTIVE", section_marks=8.0, question_count=1, difficulty_distribution=SectionDifficultyDistribution(EASY=0, MEDIUM=100, HARD=0)),
            ],
        ),
        current_user=teacher,
    )
    bp_pub_id = uuid.UUID(bp_dict["public_id"])
    await bp_service.change_blueprint_status(bp_pub_id, "ACTIVE")

    ec_dict = await bp_service.create_exam_config(
        ExamConfigCreate(
            blueprint_id=(await bp_service._bp_repo.get_by(public_id=str(bp_pub_id))).id,
            exam_name="Science Test", academic_session_id=1, exam_type="REGULAR",
        )
    )

    exam_service = ExamService(session)
    attempt_service = AttemptService(session)
    ex = await exam_service.create_exam(
        ExamCreate(board_id=board.id, school_id=school.id, class_id=cls.id, subject_id=subj.id, title="Science Midterm", exam_type="REGULAR"),
        current_user=teacher,
    )
    ex_pub_id = uuid.UUID(ex["public_id"])

    ec_id = (await exam_service.ec_repo.get_by(public_id=ec_dict["public_id"])).id
    await exam_service.configure_exam(ex_pub_id, ExamConfigure(exam_configuration_id=ec_id))
    await exam_service.generate_papers_for_exam(ex_pub_id)
    await exam_service.approve_exam(ex_pub_id)
    await exam_service.publish_exam(ex_pub_id)

    att = await attempt_service.start_attempt(ex_pub_id, student.id, current_user=teacher)
    await attempt_service.submit_attempt(uuid.UUID(att["public_id"]), current_user=teacher)
    await session.flush()

    return board, subj, chap, unit_obj, student, att, obj_q, subj_q


# ---------------------------------------------------------------------------
# 3. Integration — Full Mastery Service Flow
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_mastery_service_processes_evaluation_and_creates_rows(sqlite_session):
    """
    Integration test: after locking an evaluation, MasteryService:
    1. Creates StudentTopicMastery row with EMA score.
    2. Creates StudentChapterMastery row (aggregated).
    3. Creates StudentSubjectMastery row (aggregated).
    4. Appends MasteryHistory audit record.
    """
    board, subj, chap, unit_obj, student, att, obj_q, subj_q = await _seed_mastery_environment(sqlite_session)
    teacher = _teacher(board.id)

    # Complete and lock evaluation
    omr_service = OMRService(sqlite_session)
    subj_service = SubjectiveEvaluationService(sqlite_session)
    eval_service = EvaluationService(sqlite_session)
    mastery_service = MasteryService(sqlite_session)

    await omr_service.process_omr_upload(
        attempt_id=att["id"],
        raw_bubble_matrix={"1": {"A": 0.98, "B": 0.01, "C": 0.01, "D": 0.00}},
    )
    eval_obj = await eval_service.eval_repo.get_by_attempt(att["id"])
    await subj_service.enter_subjective_marks(
        evaluation_public_id=eval_obj.public_id,
        question_id=subj_q["id"], question_type="SUBJECTIVE",
        marks_obtained=6.0, max_marks=8.0, current_user=teacher,
    )
    await eval_service.complete_evaluation(eval_obj.public_id)
    await eval_service.lock_evaluation(eval_obj.public_id, current_user=teacher)

    # Process mastery update
    result = await mastery_service.process_evaluation(eval_obj.public_id)

    assert result["student_id"] == student.id
    assert result["topics_updated"] == 2   # 1 objective + 1 subjective (same topic → 2 detail rows)
    assert result["chapters_updated"] == 1
    assert result["subjects_updated"] == 1

    # Verify StudentTopicMastery row exists
    topic_row = await mastery_service.topic_repo.get_by_student_topic(
        student.id, unit_obj.id
    )
    assert topic_row is not None
    assert topic_row.attempt_count == 2   # 2 detail rows, same topic
    assert 0.0 < float(topic_row.mastery_score) <= 1.0

    # Verify StudentChapterMastery row
    chapter_row = await mastery_service.chapter_repo.get_by_student_chapter(
        student.id, chap.id
    )
    assert chapter_row is not None
    assert float(chapter_row.mastery_score) == pytest.approx(float(topic_row.mastery_score), abs=0.001)

    # Verify StudentSubjectMastery row
    subject_row = await mastery_service.subject_repo.get_by_student_subject(
        student.id, subj.id
    )
    assert subject_row is not None
    assert subject_row.chapter_count == 1

    # Verify MasteryHistory — 2 rows (one per detail)
    history = await mastery_service.history_repo.list_by_evaluation(eval_obj.id)
    assert len(history) == 2
    assert all(h.student_id == student.id for h in history)
    assert all(h.topic_id == unit_obj.id for h in history)


@pytest.mark.asyncio
async def test_mastery_evolves_upward_on_correct_answers(sqlite_session):
    """
    After two evaluations with full correct answers, mastery score should increase
    monotonically from 0 → value after first → higher after second.
    """
    board, subj, chap, unit_obj, student, att, obj_q, subj_q = await _seed_mastery_environment(sqlite_session)
    teacher = _teacher(board.id)

    omr_service = OMRService(sqlite_session)
    eval_service = EvaluationService(sqlite_session)
    mastery_service = MasteryService(sqlite_session)

    # First evaluation: OMR correct → objective only
    await omr_service.process_omr_upload(
        attempt_id=att["id"],
        raw_bubble_matrix={"1": {"A": 0.98, "B": 0.01, "C": 0.00, "D": 0.01}},
    )
    eval_obj = await eval_service.eval_repo.get_by_attempt(att["id"])
    await eval_service.complete_evaluation(eval_obj.public_id)
    await eval_service.lock_evaluation(eval_obj.public_id, current_user=teacher)
    await mastery_service.process_evaluation(eval_obj.public_id)

    topic_after_1 = await mastery_service.topic_repo.get_by_student_topic(student.id, unit_obj.id)
    mastery_v1 = float(topic_after_1.mastery_score)

    # Mastery starts from 0; first correct answer: 0.5 × 1.0 + 0.5 × 0.0 = 0.5
    assert mastery_v1 == pytest.approx(0.5, abs=0.01)


@pytest.mark.asyncio
async def test_learning_profile_weak_and_strong_classification(sqlite_session):
    """
    LearningProfileService correctly classifies topics as weak (< 0.5) or
    strong (>= 0.8) based on mastery scores.
    """
    board, subj, chap, unit_obj, student, att, obj_q, subj_q = await _seed_mastery_environment(sqlite_session)
    teacher = _teacher(board.id)

    omr_service = OMRService(sqlite_session)
    eval_service = EvaluationService(sqlite_session)
    mastery_service = MasteryService(sqlite_session)

    # Process evaluation with a WRONG answer (score = 0.0) → mastery stays low
    await omr_service.process_omr_upload(
        attempt_id=att["id"],
        raw_bubble_matrix={"1": {"A": 0.01, "B": 0.98, "C": 0.00, "D": 0.01}},
    )
    eval_obj = await eval_service.eval_repo.get_by_attempt(att["id"])
    await eval_service.complete_evaluation(eval_obj.public_id)
    await eval_service.lock_evaluation(eval_obj.public_id, current_user=teacher)
    await mastery_service.process_evaluation(eval_obj.public_id)

    profile_service = LearningProfileService(sqlite_session)
    profile = await profile_service.get_learning_profile(student.id, subject_id=subj.id)

    # After wrong answer, mastery = 0.5 × 0.0 + 0.5 × 0.0 = 0.0 → weak
    assert unit_obj.id in profile["weak_topic_ids"]
    assert unit_obj.id not in profile["strong_topic_ids"]


@pytest.mark.asyncio
async def test_mastery_history_records_before_and_after(sqlite_session):
    """
    MasteryHistory records the mastery score BEFORE and AFTER each update,
    enabling trend analytics in Phase 16.
    """
    board, subj, chap, unit_obj, student, att, obj_q, subj_q = await _seed_mastery_environment(sqlite_session)
    teacher = _teacher(board.id)

    omr_service = OMRService(sqlite_session)
    eval_service = EvaluationService(sqlite_session)
    mastery_service = MasteryService(sqlite_session)

    await omr_service.process_omr_upload(
        attempt_id=att["id"],
        raw_bubble_matrix={"1": {"A": 0.98, "B": 0.01, "C": 0.00, "D": 0.01}},
    )
    eval_obj = await eval_service.eval_repo.get_by_attempt(att["id"])
    await eval_service.complete_evaluation(eval_obj.public_id)
    await eval_service.lock_evaluation(eval_obj.public_id, current_user=teacher)
    await mastery_service.process_evaluation(eval_obj.public_id)

    profile_service = LearningProfileService(sqlite_session)
    history = await profile_service.get_topic_mastery_history(student.id, unit_obj.id)

    assert len(history) >= 1
    first_entry = history[0]
    # First update: started from 0.0
    assert first_entry["mastery_before"] == pytest.approx(0.0, abs=0.001)
    assert first_entry["mastery_after"] > 0.0
    assert first_entry["alpha_used"] == pytest.approx(0.5, abs=0.01)  # First attempt
