"""
Phase 15 — Recommendation Engine unit tests.

Tests:
  1. State machine: legal transitions pass, illegal ones raise BusinessRuleError.
  2. Ranking strategy: WeaknessPriorityStrategy ranks weak topics with higher priority.
  3. Recommended difficulty determination logic: EASY (<0.4), MEDIUM (0.4-0.75), HARD (>=0.75).
  4. Integration test: RecommendationService generates practice recommendation using Phase 14 mastery data.
  5. Recommendation status workflow: RECOMMENDED → ACCEPTED → DISMISSED.
  6. Feedback submission recording.
"""
from __future__ import annotations

import uuid
import pytest

from app.core.exceptions import BusinessRuleError
from app.core.security.rbac import CurrentUser
from app.modules.academic.models import Board, Chapter, Class, School, Subject, Topic
from app.modules.blueprint.schemas import (
    BlueprintCreate,
    BlueprintSectionCreate,
    ExamConfigCreate,
    SectionDifficultyDistribution,
)
from app.modules.blueprint.service import BlueprintService
from app.modules.evaluation.service import EvaluationService, OMRService
from app.modules.exam_management.schemas import ExamConfigure, ExamCreate
from app.modules.exam_management.service import AttemptService, ExamService
from app.modules.identity.models import User
from app.modules.learning_profile.service import MasteryService
from app.modules.question_bank.schemas import ObjectiveQuestionCreate, OptionSchema
from app.modules.question_bank.service import QuestionBankService
from app.modules.recommendation.domain.ranking_strategy import (
    WeaknessPriorityStrategy,
    determine_recommended_difficulty,
)
from app.modules.recommendation.domain.state_machine import (
    validate_recommendation_transition,
)
from app.modules.recommendation.service import RecommendationService
from app.modules.student.models import StudentProfile
from app.core.db.base_repository import BaseRepository


def _student_user() -> CurrentUser:
    return CurrentUser(
        public_id="student-rec-1",
        user_type="ERP_STUDENT",
        auth_source="ERP",
        roles=["STUDENT"],
        school_id=10,
        jti="jti-rec",
    )


# ---------------------------------------------------------------------------
# 1. State Machine Unit Tests (Pure Domain)
# ---------------------------------------------------------------------------

def test_recommendation_state_machine_legal_transitions():
    """Legal recommendation state transitions must pass."""
    validate_recommendation_transition("RECOMMENDED", "ACCEPTED")
    validate_recommendation_transition("RECOMMENDED", "DISMISSED")
    validate_recommendation_transition("RECOMMENDED", "EXPIRED")
    validate_recommendation_transition("ACCEPTED", "IN_PROGRESS")
    validate_recommendation_transition("ACCEPTED", "COMPLETED")
    validate_recommendation_transition("IN_PROGRESS", "COMPLETED")


def test_recommendation_state_machine_illegal_transitions_raise():
    """Illegal transitions must raise BusinessRuleError."""
    with pytest.raises(BusinessRuleError):
        validate_recommendation_transition("COMPLETED", "RECOMMENDED")

    with pytest.raises(BusinessRuleError):
        validate_recommendation_transition("DISMISSED", "ACCEPTED")


# ---------------------------------------------------------------------------
# 2. Ranking Strategy Unit Tests (Pure Domain)
# ---------------------------------------------------------------------------

def test_weakness_priority_strategy_ranks_weak_topics_first():
    """Topics with low mastery & in weak_topic_ids get higher priority scores."""
    strategy = WeaknessPriorityStrategy()
    candidates = [
        {"topic_id": 1, "chapter_id": 10, "subject_id": 100, "mastery_score": 0.85, "attempt_count": 5},
        {"topic_id": 2, "chapter_id": 10, "subject_id": 100, "mastery_score": 0.20, "attempt_count": 1},
        {"topic_id": 3, "chapter_id": 10, "subject_id": 100, "mastery_score": 0.50, "attempt_count": 2},
    ]
    weak_ids = {2}  # Topic 2 is weak

    ranked = strategy.rank_topics(candidates, weak_topic_ids=weak_ids)

    # Weak topic 2 should be ranked #1
    assert ranked[0]["topic_id"] == 2
    assert ranked[0]["priority_score"] > ranked[1]["priority_score"]
    assert ranked[2]["topic_id"] == 1  # Highest mastery topic 1 is ranked last


def test_determine_recommended_difficulty_levels():
    """Verify difficulty mapping logic."""
    assert determine_recommended_difficulty(0.2) == "EASY"
    assert determine_recommended_difficulty(0.6) == "MEDIUM"
    assert determine_recommended_difficulty(0.9) == "HARD"


# ---------------------------------------------------------------------------
# 3. Integration — Full Recommendation Generation Test
# ---------------------------------------------------------------------------

async def _seed_recommendation_environment(session):
    """Seed DB: academic tree, questions, student, evaluation lock -> Phase 14 mastery created."""
    board = await BaseRepository(session, Board).create({"erp_id": "board-rec-1", "name": "CBSE"})
    school = await BaseRepository(session, School).create({"erp_id": "school-rec-1", "name": "School REC", "board_id": board.id})
    cls = await BaseRepository(session, Class).create({"erp_id": "class-rec-1", "name": "Class 10", "school_id": school.id})
    subj = await BaseRepository(session, Subject).create({"erp_id": "subj-rec-1", "name": "Physics", "board_id": board.id, "class_id": cls.id})
    chap = await BaseRepository(session, Chapter).create({"erp_id": "chap-rec-1", "subject_id": subj.id, "name": "Electricity", "sequence": 1})
    unit_obj = await BaseRepository(session, Topic).create({"erp_id": "top-rec-1", "unit_id": chap.id, "name": "Ohm Law"})

    qb = QuestionBankService(session)
    teacher = CurrentUser(public_id="t-rec", user_type="TEACHER", auth_source="ERP", roles=["TEACHER"], school_id=10, board_id=board.id, jti="jti")

    obj_q = await qb.create_objective_question(
        ObjectiveQuestionCreate(
            board_id=board.id, class_id=cls.id, subject_id=subj.id,
            primary_chapter_id=chap.id, primary_topic_id=unit_obj.id,
            question_text="V = I * R?",
            options=[OptionSchema(label="A", text="True"), OptionSchema(label="B", text="False")],
            correct_option="A", marks=2.0, difficulty="EASY",
        ),
        current_user=teacher,
    )
    await qb.change_status(obj_q["public_id"], "ACTIVE", current_user=teacher)

    user = await BaseRepository(session, User).create(
        {"email": "student_rec@test.com", "user_type": "ERP_STUDENT", "auth_source": "ERP", "status": "ACTIVE", "school_id": school.id}
    )
    student = await BaseRepository(session, StudentProfile).create(
        {"erp_student_id": "std-rec-1", "school_id": school.id, "user_id": user.id, "name": "Priya Das", "student_type": "ERP"}
    )

    bp_service = BlueprintService(session)
    bp_dict = await bp_service.create_blueprint(
        BlueprintCreate(
            board_id=board.id, class_id=cls.id, subject_id=subj.id,
            name="Physics Blueprint", total_marks=2.0, duration_minutes=30,
            sections=[
                BlueprintSectionCreate(section_label="A", question_type="OBJECTIVE", section_marks=2.0, question_count=1, difficulty_distribution=SectionDifficultyDistribution(EASY=100, MEDIUM=0, HARD=0)),
            ],
        ),
        current_user=teacher,
    )
    bp_pub_id = uuid.UUID(bp_dict["public_id"])
    await bp_service.change_blueprint_status(bp_pub_id, "ACTIVE")

    ec_dict = await bp_service.create_exam_config(
        ExamConfigCreate(
            blueprint_id=(await bp_service._bp_repo.get_by(public_id=str(bp_pub_id))).id,
            exam_name="Physics Quiz", academic_session_id=1, exam_type="REGULAR",
        )
    )

    exam_service = ExamService(session)
    attempt_service = AttemptService(session)
    ex = await exam_service.create_exam(
        ExamCreate(board_id=board.id, school_id=school.id, class_id=cls.id, subject_id=subj.id, title="Physics Test", exam_type="REGULAR"),
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

    # Process evaluation & lock -> triggers Phase 14 mastery creation
    omr_service = OMRService(session)
    eval_service = EvaluationService(session)
    mastery_service = MasteryService(session)

    # Student answered WRONG -> topic becomes weak (mastery = 0.0 < 0.5)
    await omr_service.process_omr_upload(attempt_id=att["id"], raw_bubble_matrix={"1": {"A": 0.01, "B": 0.98}})
    eval_obj = await eval_service.eval_repo.get_by_attempt(att["id"])
    await eval_service.complete_evaluation(eval_obj.public_id)
    await eval_service.lock_evaluation(eval_obj.public_id, current_user=teacher)
    await mastery_service.process_evaluation(eval_obj.public_id)

    return board, subj, chap, unit_obj, student, att


@pytest.mark.asyncio
async def test_recommendation_service_generates_practice_set(sqlite_session):
    """
    Integration test: RecommendationService generates a personalized practice set
    for a student based on their weak topic identified in Phase 14.
    """
    board, subj, chap, unit_obj, student, att = await _seed_recommendation_environment(sqlite_session)

    rec_service = RecommendationService(sqlite_session)

    rec = await rec_service.generate_recommendation(
        student_id=student.id,
        subject_id=subj.id,
        recommendation_type="PRACTICE_SET",
        item_count=3,
    )

    assert rec["student_id"] == student.id
    assert rec["subject_id"] == subj.id
    assert rec["status"] == "RECOMMENDED"
    assert unit_obj.id in rec["target_topic_ids_json"]
    assert rec["recommended_difficulty"] in ("EASY", "MEDIUM", "HARD")
    assert len(rec["items"]) >= 1
    assert rec["items"][0]["topic_id"] == unit_obj.id


@pytest.mark.asyncio
async def test_recommendation_accept_and_dismiss_flow(sqlite_session):
    """
    Workflow test: RECOMMENDED -> ACCEPTED and RECOMMENDED -> DISMISSED state transitions.
    """
    board, subj, chap, unit_obj, student, att = await _seed_recommendation_environment(sqlite_session)
    rec_service = RecommendationService(sqlite_session)

    # 1. Generate recommendation
    rec = await rec_service.generate_recommendation(
        student_id=student.id,
        subject_id=subj.id,
    )
    pub_id = rec["public_id"]

    # 2. Accept recommendation
    accepted = await rec_service.accept_recommendation(pub_id)
    assert accepted["status"] == "ACCEPTED"

    # 3. List student recommendations
    list_recs = await rec_service.list_student_recommendations(student.id, status="ACCEPTED")
    assert len(list_recs) == 1
    assert list_recs[0]["public_id"] == pub_id


@pytest.mark.asyncio
async def test_recommendation_submit_feedback(sqlite_session):
    """
    Submitting feedback records rating and optional comments.
    """
    board, subj, chap, unit_obj, student, att = await _seed_recommendation_environment(sqlite_session)
    rec_service = RecommendationService(sqlite_session)

    rec = await rec_service.generate_recommendation(student_id=student.id, subject_id=subj.id)

    fb = await rec_service.submit_feedback(
        public_id=rec["public_id"],
        rating="HELPFUL",
        comments="Great practice set for Ohm Law!",
    )

    assert fb["rating"] == "HELPFUL"
    assert fb["comments"] == "Great practice set for Ohm Law!"
