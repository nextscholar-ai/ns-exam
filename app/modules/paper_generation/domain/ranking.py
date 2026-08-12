"""
Paper Generation domain — Candidate Ranking (Phase 11 §7).

Pure functions: no DB calls, no side effects.
Input: a list of candidate dicts + scoring parameters.
Output: same list, sorted by final_rank_score descending.

Scoring criteria (all normalized 0.0–1.0):
  1. blueprint_match   — question type matches section requirement.
  2. difficulty_match  — difficulty matches slot target.
  3. weak_topic_match  — question's topic is in student's weak_topics.
  4. usage_balance     — prefer questions with lower usage_count.
  5. bloom_match       — bloom_level matches slot target.

Final score = weighted average of all criteria.
Default weights are configurable per call to allow future tuning without
touching business logic (Phase 21 §7 future expansion note).
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Default criterion weights — sum must equal 1.0
# ---------------------------------------------------------------------------
DEFAULT_WEIGHTS: dict[str, float] = {
    "blueprint_match": 0.25,
    "difficulty_match": 0.25,
    "weak_topic_match": 0.20,
    "usage_balance": 0.15,
    "bloom_match": 0.15,
}


@dataclass
class RankingCriteria:
    """
    Encapsulates all parameters needed to rank a single slot's candidates.

    target_difficulty:  required difficulty for this slot ("EASY"|"MEDIUM"|"HARD")
    target_bloom:       required Bloom level for this slot (may be None)
    question_type:      required question type for the section
    weak_topic_ids:     set of topic IDs the student is weak in (empty for non-personalized)
    already_selected:   set of (question_type, question_id) already in this paper — avoids duplicates
    max_usage_count:    maximum usage_count seen across all candidates — used for normalization
    weights:            criterion weight dict (defaults to DEFAULT_WEIGHTS)
    """

    target_difficulty: str
    target_bloom: str | None = None
    question_type: str = "OBJECTIVE"
    weak_topic_ids: set[int] = field(default_factory=set)
    already_selected: set[tuple[str, int]] = field(default_factory=set)
    max_usage_count: int = 1
    weights: dict[str, float] = field(default_factory=lambda: dict(DEFAULT_WEIGHTS))


@dataclass
class ScoredCandidate:
    """One candidate with all per-criterion scores and final rank."""

    candidate: dict[str, Any]
    blueprint_match_score: float
    difficulty_match_score: float
    weak_topic_match_score: float
    usage_balance_score: float
    bloom_match_score: float
    final_rank_score: float

    def as_reason_dict(self) -> dict[str, float]:
        """Returns scores suitable for PaperQuestion.selection_reason_json."""
        return {
            "blueprint_match": self.blueprint_match_score,
            "difficulty_match": self.difficulty_match_score,
            "weak_topic_match": self.weak_topic_match_score,
            "usage_balance": self.usage_balance_score,
            "bloom_match": self.bloom_match_score,
            "final_rank": self.final_rank_score,
        }


# ---------------------------------------------------------------------------
# Scoring helpers — each returns 0.0 or 1.0 (binary match for v1)
# ---------------------------------------------------------------------------

def _score_blueprint(candidate: dict, criteria: RankingCriteria) -> float:
    """1.0 if question_type matches the section requirement."""
    return 1.0 if candidate.get("question_type") == criteria.question_type else 0.0


def _score_difficulty(candidate: dict, criteria: RankingCriteria) -> float:
    """1.0 if difficulty matches the slot target."""
    return 1.0 if candidate.get("difficulty") == criteria.target_difficulty else 0.0


def _score_weak_topic(candidate: dict, criteria: RankingCriteria) -> float:
    """
    1.0 if question's primary_topic_id is in student's weak topics.
    0.0 for non-personalized papers (weak_topic_ids is empty).
    """
    if not criteria.weak_topic_ids:
        return 0.0
    topic_id = candidate.get("primary_topic_id")
    return 1.0 if topic_id in criteria.weak_topic_ids else 0.0


def _score_usage_balance(candidate: dict, criteria: RankingCriteria) -> float:
    """
    Prefer less-used questions — linearly inverted usage count.
    Score = 1 - (usage_count / max_usage_count), floored at 0.
    """
    usage = candidate.get("usage_count", 0)
    denom = max(criteria.max_usage_count, 1)
    return max(0.0, 1.0 - usage / denom)


def _score_bloom(candidate: dict, criteria: RankingCriteria) -> float:
    """1.0 if bloom_level matches the slot target (or no target given)."""
    if criteria.target_bloom is None:
        return 1.0
    return 1.0 if candidate.get("bloom_level") == criteria.target_bloom else 0.0


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def score_candidate(
    candidate: dict[str, Any],
    criteria: RankingCriteria,
) -> ScoredCandidate:
    """
    Compute all per-criterion scores and the weighted final rank for one candidate.
    """
    w = criteria.weights
    scores = {
        "blueprint_match": _score_blueprint(candidate, criteria),
        "difficulty_match": _score_difficulty(candidate, criteria),
        "weak_topic_match": _score_weak_topic(candidate, criteria),
        "usage_balance": _score_usage_balance(candidate, criteria),
        "bloom_match": _score_bloom(candidate, criteria),
    }
    final = sum(w.get(k, 0.0) * v for k, v in scores.items())

    return ScoredCandidate(
        candidate=candidate,
        blueprint_match_score=scores["blueprint_match"],
        difficulty_match_score=scores["difficulty_match"],
        weak_topic_match_score=scores["weak_topic_match"],
        usage_balance_score=scores["usage_balance"],
        bloom_match_score=scores["bloom_match"],
        final_rank_score=round(final, 6),
    )


def rank_candidates(
    candidates: list[dict[str, Any]],
    criteria: RankingCriteria,
    top_n: int = 5,
) -> list[ScoredCandidate]:
    """
    Score and sort all candidates; exclude already-selected ones.

    Returns top_n ScoredCandidate objects (all scored for AI log, best first).
    Randomization only among tied final scores (Phase 11 §7).
    """
    # Pre-compute max usage_count for normalization
    counts = [c.get("usage_count", 0) for c in candidates]
    criteria.max_usage_count = max(counts, default=1) if counts else 1

    scored = [
        score_candidate(c, criteria)
        for c in candidates
        if (c.get("question_type"), c.get("id")) not in criteria.already_selected
    ]

    # Sort: final_rank descending, then shuffle within ties for variety
    scored.sort(key=lambda s: s.final_rank_score, reverse=True)

    # Break ties randomly (Phase 11 §7 — only among equal top scorers)
    if len(scored) > 1 and scored[0].final_rank_score == scored[1].final_rank_score:
        top_score = scored[0].final_rank_score
        tied = [s for s in scored if s.final_rank_score == top_score]
        rest = [s for s in scored if s.final_rank_score != top_score]
        random.shuffle(tied)
        scored = tied + rest

    return scored[:top_n]


def pick_best(ranked: list[ScoredCandidate]) -> ScoredCandidate | None:
    """Return the top-ranked candidate, or None if the list is empty."""
    return ranked[0] if ranked else None
