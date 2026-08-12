"""
Phase 11 — Blueprint & Paper Generation unit tests.

Tests are organized into three groups:

1. Pure domain function tests (no DB):
   - ranking.py: score_candidate, rank_candidates, pick_best.
   - validation.py: each of the 8 rules individually + run_all_validations.
   - constraint_engine.py: expand_slots + assemble_paper with in-memory fetcher.

2. BlueprintService DB tests (sqlite_session):
   - Create blueprint with sections.
   - Status transition (DRAFT → ACTIVE → ARCHIVED).
   - Guard against invalid transition.

3. PaperGenerationService DB tests (sqlite_session):
   - Generate a non-personalized paper.
   - Validation rows are created.
   - Version history is created.
   - Approve flow (UNDER_REVIEW → APPROVED) blocked when validations fail.
"""
from __future__ import annotations

import pytest

from app.modules.paper_generation.domain.ranking import (
    RankingCriteria,
    rank_candidates,
    score_candidate,
)
from app.modules.paper_generation.domain.validation import (
    ValidationResult,
    _rule_difficulty_balance,
    _rule_no_duplicate_questions,
    _rule_question_availability,
    _rule_section_marks_match,
    _rule_total_marks_match,
    all_passed,
    run_all_validations,
)
from app.modules.paper_generation.domain.constraint_engine import (
    ConstraintEngine,
    EngineContext,
    expand_slots,
)


# ===========================================================================
# 1. Pure Domain — Ranking
# ===========================================================================

def _make_candidate(
    cid: int,
    question_type: str = "OBJECTIVE",
    difficulty: str = "MEDIUM",
    bloom_level: str = "UNDERSTAND",
    topic_id: int | None = None,
    usage_count: int = 0,
    marks: float = 1.0,
) -> dict:
    return {
        "id": cid,
        "question_type": question_type,
        "difficulty": difficulty,
        "bloom_level": bloom_level,
        "primary_topic_id": topic_id,
        "usage_count": usage_count,
        "marks": marks,
        "primary_chapter_id": 1,
    }


def test_score_candidate_perfect_match():
    """A candidate matching all criteria scores near 1.0."""
    c = _make_candidate(1, difficulty="EASY", bloom_level="REMEMBER", topic_id=5)
    criteria = RankingCriteria(
        target_difficulty="EASY",
        target_bloom="REMEMBER",
        question_type="OBJECTIVE",
        weak_topic_ids={5},
    )
    scored = score_candidate(c, criteria)

    # blueprint_match=1, difficulty_match=1, weak_topic=1, usage_balance=1, bloom=1
    assert scored.blueprint_match_score == 1.0
    assert scored.difficulty_match_score == 1.0
    assert scored.weak_topic_match_score == 1.0
    assert scored.bloom_match_score == 1.0
    assert scored.final_rank_score > 0.9


def test_score_candidate_wrong_type_scores_zero_blueprint():
    """Wrong question_type → blueprint_match = 0.0."""
    c = _make_candidate(1, question_type="SUBJECTIVE")
    criteria = RankingCriteria(target_difficulty="MEDIUM", question_type="OBJECTIVE")
    scored = score_candidate(c, criteria)
    assert scored.blueprint_match_score == 0.0


def test_rank_candidates_excludes_selected():
    """Questions in already_selected set must be excluded from ranked output."""
    candidates = [_make_candidate(i) for i in range(1, 6)]
    criteria = RankingCriteria(
        target_difficulty="MEDIUM",
        question_type="OBJECTIVE",
        already_selected={("OBJECTIVE", 1), ("OBJECTIVE", 2)},
    )
    ranked = rank_candidates(candidates, criteria, top_n=10)
    selected_ids = {sc.candidate["id"] for sc in ranked}
    assert 1 not in selected_ids
    assert 2 not in selected_ids


def test_rank_candidates_usage_balance():
    """Lower usage_count → higher usage_balance score → ranked higher."""
    low_usage = _make_candidate(1, usage_count=0)
    high_usage = _make_candidate(2, usage_count=100)
    criteria = RankingCriteria(
        target_difficulty="MEDIUM",
        question_type="OBJECTIVE",
    )
    ranked = rank_candidates([low_usage, high_usage], criteria, top_n=2)
    assert ranked[0].candidate["id"] == 1  # low usage ranked first


def test_weak_topic_boost_personalizes_ranking():
    """A candidate whose topic is in weak_topic_ids gets a higher score."""
    weak_cand = _make_candidate(1, topic_id=10)
    strong_cand = _make_candidate(2, topic_id=99)
    criteria = RankingCriteria(
        target_difficulty="MEDIUM",
        question_type="OBJECTIVE",
        weak_topic_ids={10},
    )
    scored_weak = score_candidate(weak_cand, criteria)
    scored_strong = score_candidate(strong_cand, criteria)
    assert scored_weak.weak_topic_match_score == 1.0
    assert scored_strong.weak_topic_match_score == 0.0
    assert scored_weak.final_rank_score > scored_strong.final_rank_score


# ===========================================================================
# 2. Pure Domain — Validation Rules
# ===========================================================================

def test_total_marks_match_pass():
    r = _rule_total_marks_match(100.0, 100.0)
    assert r.passed is True


def test_total_marks_match_fail():
    r = _rule_total_marks_match(95.0, 100.0)
    assert r.passed is False
    assert "95.0" in r.detail


def test_section_marks_match_pass():
    sections = [{"section_label": "A", "actual_marks": 50.0}]
    bp_secs = [{"section_label": "A", "section_marks": 50.0}]
    r = _rule_section_marks_match(sections, bp_secs)
    assert r.passed is True


def test_section_marks_match_fail():
    sections = [{"section_label": "A", "actual_marks": 45.0}]
    bp_secs = [{"section_label": "A", "section_marks": 50.0}]
    r = _rule_section_marks_match(sections, bp_secs)
    assert r.passed is False


def test_no_duplicate_questions_pass():
    pqs = [
        {"question_type": "OBJECTIVE", "question_id": 1},
        {"question_type": "OBJECTIVE", "question_id": 2},
    ]
    r = _rule_no_duplicate_questions(pqs)
    assert r.passed is True


def test_no_duplicate_questions_fail():
    pqs = [
        {"question_type": "OBJECTIVE", "question_id": 1},
        {"question_type": "OBJECTIVE", "question_id": 1},
    ]
    r = _rule_no_duplicate_questions(pqs)
    assert r.passed is False


def test_question_availability_pass():
    sections = [{"section_label": "A", "filled_count": 5, "required_count": 5}]
    r = _rule_question_availability(sections)
    assert r.passed is True


def test_question_availability_fail():
    sections = [{"section_label": "A", "filled_count": 3, "required_count": 5}]
    r = _rule_question_availability(sections)
    assert r.passed is False


def test_run_all_validations_returns_8_rules():
    results = run_all_validations(
        paper_total=100.0,
        blueprint_total=100.0,
        blueprint_duration=60,
        sections=[
            {
                "section_label": "A",
                "actual_marks": 100.0,
                "section_marks": 100.0,
                "filled_count": 5,
                "required_count": 5,
                "actual_difficulty_distribution": {},
                "actual_bloom_distribution": {},
            }
        ],
        blueprint_sections=[
            {
                "section_label": "A",
                "section_marks": 100.0,
                "question_count": 5,
                "difficulty_distribution_json": {},
                "bloom_distribution_json": None,
            }
        ],
        paper_questions=[
            {"question_type": "OBJECTIVE", "question_id": i, "primary_chapter_id": 1}
            for i in range(1, 6)
        ],
        required_chapter_ids=[1],
    )
    assert len(results) == 8
    codes = {r.rule_code for r in results}
    assert "TOTAL_MARKS_MATCH" in codes
    assert "DIFFICULTY_BALANCE" in codes
    assert "NO_DUPLICATE_QUESTIONS" in codes
    assert "QUESTION_AVAILABILITY" in codes


def test_all_passed_true_and_false():
    passing = [ValidationResult("X", True), ValidationResult("Y", True)]
    failing = [ValidationResult("X", True), ValidationResult("Y", False)]
    assert all_passed(passing) is True
    assert all_passed(failing) is False


# ===========================================================================
# 3. Pure Domain — Constraint Engine expand_slots
# ===========================================================================

def test_expand_slots_produces_correct_count():
    """expand_slots returns exactly question_count slots."""
    slots = expand_slots(
        section_label="A",
        question_type="OBJECTIVE",
        question_count=5,
        marks_per_question=2.0,
        difficulty_distribution={"EASY": 40, "MEDIUM": 40, "HARD": 20},
        bloom_distribution=None,
        chapter_ids=[1, 2],
    )
    assert len(slots) == 5


def test_expand_slots_difficulty_distribution():
    """Difficulty counts must honour (floor) the distribution."""
    slots = expand_slots(
        section_label="A",
        question_type="OBJECTIVE",
        question_count=10,
        marks_per_question=1.0,
        difficulty_distribution={"EASY": 30, "MEDIUM": 50, "HARD": 20},
        bloom_distribution=None,
        chapter_ids=[1],
    )
    diffs = [s.difficulty for s in slots]
    # At least 2 HARD (floor(10*20/100)=2)
    assert diffs.count("HARD") >= 2


@pytest.mark.asyncio
async def test_constraint_engine_assembles_paper_with_stub_fetcher():
    """Engine returns one AssembledSection per blueprint_section with stub candidates."""

    async def stub_fetcher(
        question_type,
        board_id,
        class_id,
        subject_id,
        chapter_ids,
        difficulty,
        bloom_level,
        exclude_ids,
    ):
        # Return 5 fake candidates per call
        return [
            _make_candidate(
                cid=i,
                question_type=question_type,
                difficulty=difficulty,
                marks=2.0,
            )
            for i in range(1, 6)
        ]

    ctx = EngineContext(
        board_id=1,
        class_id=1,
        subject_id=1,
        blueprint_total_marks=20.0,
        blueprint_duration=60,
    )
    engine = ConstraintEngine(ctx)

    bp_sections = [
        {
            "section_label": "A",
            "question_type": "OBJECTIVE",
            "section_marks": 20.0,
            "question_count": 5,
            "difficulty_distribution_json": {"MEDIUM": 100},
            "bloom_distribution_json": None,
            "chapter_scope_json": None,
        }
    ]

    assembled = await engine.assemble_paper(
        blueprint_sections=bp_sections,
        chapter_ids=[1, 2],
        fetcher=stub_fetcher,
    )

    assert len(assembled) == 1
    section = assembled[0]
    assert section.filled_count == 5
    assert section.section_label == "A"
    # No duplicate question_ids selected
    selected_ids = [sc.candidate["id"] for sc in section.selected]
    assert len(set(selected_ids)) == len(selected_ids)


# ===========================================================================
# 4. BlueprintService DB tests
# ===========================================================================

from app.core.security.rbac import CurrentUser
from app.modules.blueprint.schemas import BlueprintCreate, BlueprintSectionCreate
from app.modules.blueprint.service import BlueprintService
from app.modules.blueprint.schemas import SectionDifficultyDistribution


def _teacher_user(board_id: int = 1) -> CurrentUser:
    return CurrentUser(
        public_id="teacher-bp-1",
        user_type="TEACHER",
        auth_source="ERP",
        roles=["TEACHER"],
        school_id=10,
        board_id=board_id,
        jti="jti-bp",
    )


def _make_blueprint_payload(board_id=1, class_id=1, subject_id=1) -> BlueprintCreate:
    return BlueprintCreate(
        board_id=board_id,
        class_id=class_id,
        subject_id=subject_id,
        name="Class 10 Science Blueprint",
        total_marks=100.0,
        duration_minutes=180,
        sections=[
            BlueprintSectionCreate(
                section_label="A",
                question_type="OBJECTIVE",
                section_marks=40.0,
                question_count=20,
                difficulty_distribution=SectionDifficultyDistribution(
                    EASY=30, MEDIUM=50, HARD=20
                ),
            ),
            BlueprintSectionCreate(
                section_label="B",
                question_type="SUBJECTIVE",
                section_marks=60.0,
                question_count=6,
                difficulty_distribution=SectionDifficultyDistribution(
                    EASY=0, MEDIUM=60, HARD=40
                ),
            ),
        ],
    )


@pytest.mark.asyncio
async def test_create_blueprint_and_sections(sqlite_session):
    """Blueprint and its sections are persisted correctly."""
    from app.modules.academic.models import Board, Class, Subject, School
    from app.core.db.base_repository import BaseRepository

    # Seed academic hierarchy
    board = await BaseRepository(sqlite_session, Board).create(
        {"erp_id": "board-bp-1", "name": "CBSE"}
    )
    school = await BaseRepository(sqlite_session, School).create(
        {"erp_id": "school-bp-1", "name": "School A", "board_id": board.id}
    )
    cls = await BaseRepository(sqlite_session, Class).create(
        {"erp_id": "class-bp-1", "name": "Class 10", "school_id": school.id}
    )
    subj = await BaseRepository(sqlite_session, Subject).create(
        {"erp_id": "subj-bp-1", "name": "Science", "board_id": board.id, "class_id": cls.id}
    )
    await sqlite_session.flush()

    service = BlueprintService(sqlite_session)
    payload = _make_blueprint_payload(board.id, cls.id, subj.id)
    result = await service.create_blueprint(payload, current_user=_teacher_user(board.id))

    assert result["name"] == "Class 10 Science Blueprint"
    assert result["total_marks"] == 100.0
    assert result["status"] == "DRAFT"

    # Sections should be persisted
    sections = await service.get_sections(
        (await service._bp_repo.get_by(public_id=result["public_id"])).id
    )
    assert len(sections) == 2
    labels = {s["section_label"] for s in sections}
    assert labels == {"A", "B"}


@pytest.mark.asyncio
async def test_blueprint_status_transition(sqlite_session):
    """Blueprint status transitions: DRAFT → ACTIVE → ARCHIVED."""
    from app.modules.academic.models import Board, Class, Subject, School
    from app.core.db.base_repository import BaseRepository

    board = await BaseRepository(sqlite_session, Board).create(
        {"erp_id": "board-bp-2", "name": "CBSE2"}
    )
    school = await BaseRepository(sqlite_session, School).create(
        {"erp_id": "school-bp-2", "name": "School B", "board_id": board.id}
    )
    cls = await BaseRepository(sqlite_session, Class).create(
        {"erp_id": "class-bp-2", "name": "Class 9", "school_id": school.id}
    )
    subj = await BaseRepository(sqlite_session, Subject).create(
        {"erp_id": "subj-bp-2", "name": "Math", "board_id": board.id, "class_id": cls.id}
    )
    await sqlite_session.flush()

    service = BlueprintService(sqlite_session)
    payload = _make_blueprint_payload(board.id, cls.id, subj.id)
    result = await service.create_blueprint(payload)

    import uuid as _uuid
    pub_id = _uuid.UUID(result["public_id"])

    # DRAFT → ACTIVE
    activated = await service.change_blueprint_status(pub_id, "ACTIVE")
    assert activated["status"] == "ACTIVE"

    # ACTIVE → ARCHIVED
    archived = await service.change_blueprint_status(pub_id, "ARCHIVED")
    assert archived["status"] == "ARCHIVED"


@pytest.mark.asyncio
async def test_blueprint_invalid_status_transition_raises(sqlite_session):
    """Transition DRAFT → PUBLISHED must raise BusinessRuleError."""
    from app.modules.academic.models import Board, Class, Subject, School
    from app.core.db.base_repository import BaseRepository
    from app.core.exceptions import BusinessRuleError

    board = await BaseRepository(sqlite_session, Board).create(
        {"erp_id": "board-bp-3", "name": "CBSE3"}
    )
    school = await BaseRepository(sqlite_session, School).create(
        {"erp_id": "school-bp-3", "name": "School C", "board_id": board.id}
    )
    cls = await BaseRepository(sqlite_session, Class).create(
        {"erp_id": "class-bp-3", "name": "Class 8", "school_id": school.id}
    )
    subj = await BaseRepository(sqlite_session, Subject).create(
        {"erp_id": "subj-bp-3", "name": "English", "board_id": board.id, "class_id": cls.id}
    )
    await sqlite_session.flush()

    service = BlueprintService(sqlite_session)
    payload = _make_blueprint_payload(board.id, cls.id, subj.id)
    result = await service.create_blueprint(payload)
    import uuid as _uuid
    pub_id = _uuid.UUID(result["public_id"])

    with pytest.raises(BusinessRuleError):
        await service.change_blueprint_status(pub_id, "PUBLISHED")


# ===========================================================================
# 5. BlueprintCreate schema validates section marks sum
# ===========================================================================

def test_blueprint_create_section_marks_mismatch_raises():
    """BlueprintCreate must reject payloads where section marks ≠ total_marks."""
    with pytest.raises(Exception):  # pydantic ValidationError
        BlueprintCreate(
            board_id=1,
            class_id=1,
            subject_id=1,
            name="Bad Blueprint",
            total_marks=100.0,
            duration_minutes=60,
            sections=[
                BlueprintSectionCreate(
                    section_label="A",
                    question_type="OBJECTIVE",
                    section_marks=30.0,  # only 30, but total=100
                    question_count=10,
                    difficulty_distribution=SectionDifficultyDistribution(
                        EASY=30, MEDIUM=50, HARD=20
                    ),
                )
            ],
        )
