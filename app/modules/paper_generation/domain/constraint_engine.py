"""
Paper Generation domain — AI Constraint Engine (Phase 11 §7).

This module orchestrates the slot-by-slot candidate selection loop:

  For each BlueprintSection:
    Expand the section into individual difficulty slots based on
    difficulty_distribution_json (e.g. 40% EASY, 40% MEDIUM, 20% HARD).

    For each slot:
      1. Fetch candidates from QuestionBankService.
      2. Apply learning-profile weak-topic boost (read-only, Phase 11 §5).
      3. Rank via ranking.py.
      4. Log all top-N to ai_generation_logs.
      5. Pick best; add to paper_in_progress.

  Run blueprint_validation at the end (validation.py).

Design:
  - Stateless dataclasses carry all context — no class-level mutation.
  - The engine itself has NO DB access — it receives pre-fetched candidates
    via the CandidateFetcher protocol, so it is fully unit-testable with
    in-memory stubs.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Protocol

from app.modules.paper_generation.domain.ranking import (
    RankingCriteria,
    ScoredCandidate,
    pick_best,
    rank_candidates,
)


# ---------------------------------------------------------------------------
# Protocol for candidate fetching (injected dependency — testable stub-able)
# ---------------------------------------------------------------------------

class CandidateFetcher(Protocol):
    """
    Async callable that returns candidate question dicts for a slot.
    Injected by PaperGenerationService so the engine has no DB imports.
    """

    async def __call__(
        self,
        question_type: str,
        board_id: int,
        class_id: int,
        subject_id: int,
        chapter_ids: list[int],
        difficulty: str,
        bloom_level: str | None,
        exclude_ids: set[tuple[str, int]],
    ) -> list[dict[str, Any]]:
        ...


# ---------------------------------------------------------------------------
# Dataclasses carrying engine context
# ---------------------------------------------------------------------------

@dataclass
class Slot:
    """One question slot expanded from a BlueprintSection rule."""

    section_label: str
    question_type: str
    difficulty: str
    bloom_level: str | None
    marks_per_question: float
    chapter_ids: list[int]


@dataclass
class EngineContext:
    """All parameters the constraint engine needs for one paper generation run."""

    board_id: int
    class_id: int
    subject_id: int
    blueprint_total_marks: float
    blueprint_duration: int
    weak_topic_ids: set[int] = field(default_factory=set)
    top_n_log: int = 5  # number of candidates to log per slot


@dataclass
class AssembledSection:
    """Accumulates selected questions for one section during assembly."""

    section_label: str
    question_type: str
    section_marks: float
    required_count: int
    selected: list[ScoredCandidate] = field(default_factory=list)
    all_logged_candidates: list[ScoredCandidate] = field(default_factory=list)

    @property
    def filled_count(self) -> int:
        return len(self.selected)

    @property
    def actual_marks(self) -> float:
        return sum(sc.candidate.get("marks", 0) for sc in self.selected)

    @property
    def actual_difficulty_distribution(self) -> dict[str, float]:
        if not self.selected:
            return {}
        counts: dict[str, int] = {}
        for sc in self.selected:
            d = sc.candidate.get("difficulty", "MEDIUM")
            counts[d] = counts.get(d, 0) + 1
        total = len(self.selected)
        return {k: round(v / total * 100, 1) for k, v in counts.items()}

    @property
    def actual_bloom_distribution(self) -> dict[str, float]:
        if not self.selected:
            return {}
        counts: dict[str, int] = {}
        for sc in self.selected:
            b = sc.candidate.get("bloom_level", "UNDERSTAND")
            counts[b] = counts.get(b, 0) + 1
        total = len(self.selected)
        return {k: round(v / total * 100, 1) for k, v in counts.items()}


# ---------------------------------------------------------------------------
# Slot expansion
# ---------------------------------------------------------------------------

def expand_slots(
    section_label: str,
    question_type: str,
    question_count: int,
    marks_per_question: float,
    difficulty_distribution: dict[str, int],
    bloom_distribution: dict[str, int] | None,
    chapter_ids: list[int],
) -> list[Slot]:
    """
    Expand a BlueprintSection into individual Slot objects.

    Difficulty distribution is percentage-based; convert to counts.
    Bloom distribution (if given) rotates bloom level targets across slots.
    """
    slots: list[Slot] = []
    difficulties_flat: list[str] = []

    for diff, pct in difficulty_distribution.items():
        count = max(1, math.floor(question_count * pct / 100))
        difficulties_flat.extend([diff] * count)

    # Pad/trim to exact question_count
    while len(difficulties_flat) < question_count:
        difficulties_flat.append("MEDIUM")
    difficulties_flat = difficulties_flat[:question_count]

    # Expand bloom levels similarly (if specified)
    bloom_levels: list[str | None] = [None] * question_count
    if bloom_distribution:
        blooms_flat: list[str] = []
        for lvl, pct in bloom_distribution.items():
            count = max(1, math.floor(question_count * pct / 100))
            blooms_flat.extend([lvl] * count)
        while len(blooms_flat) < question_count:
            blooms_flat.append(None)
        bloom_levels = blooms_flat[:question_count]

    for i in range(question_count):
        slots.append(
            Slot(
                section_label=section_label,
                question_type=question_type,
                difficulty=difficulties_flat[i],
                bloom_level=bloom_levels[i],
                marks_per_question=marks_per_question,
                chapter_ids=chapter_ids,
            )
        )

    return slots


# ---------------------------------------------------------------------------
# Constraint Engine
# ---------------------------------------------------------------------------

class ConstraintEngine:
    """
    Deterministic, rule-based paper assembly engine (Phase 11 §7).

    No LLM — no calls to external AI services (Phase 1 §13).
    Randomization only applied among candidates with identical final scores.
    """

    def __init__(self, context: EngineContext) -> None:
        self._ctx = context

    async def assemble_paper(
        self,
        blueprint_sections: list[dict[str, Any]],
        chapter_ids: list[int],
        fetcher: CandidateFetcher,
    ) -> list[AssembledSection]:
        """
        Main entry point: iterate sections → slots → select → assemble.

        Returns one AssembledSection per blueprint section.
        """
        already_selected: set[tuple[str, int]] = set()
        assembled: list[AssembledSection] = []

        for bp_sec in blueprint_sections:
            marks_per_q = (
                bp_sec["section_marks"] / bp_sec["question_count"]
                if bp_sec["question_count"] > 0
                else 0.0
            )
            sec_chapters = bp_sec.get("chapter_scope_json") or chapter_ids

            slots = expand_slots(
                section_label=bp_sec["section_label"],
                question_type=bp_sec["question_type"],
                question_count=bp_sec["question_count"],
                marks_per_question=marks_per_q,
                difficulty_distribution=bp_sec.get(
                    "difficulty_distribution_json", {"MEDIUM": 100}
                ),
                bloom_distribution=bp_sec.get("bloom_distribution_json"),
                chapter_ids=sec_chapters,
            )

            asm = AssembledSection(
                section_label=bp_sec["section_label"],
                question_type=bp_sec["question_type"],
                section_marks=bp_sec["section_marks"],
                required_count=bp_sec["question_count"],
            )

            for slot in slots:
                candidates = await fetcher(
                    question_type=slot.question_type,
                    board_id=self._ctx.board_id,
                    class_id=self._ctx.class_id,
                    subject_id=self._ctx.subject_id,
                    chapter_ids=slot.chapter_ids,
                    difficulty=slot.difficulty,
                    bloom_level=slot.bloom_level,
                    exclude_ids=already_selected,
                )

                criteria = RankingCriteria(
                    target_difficulty=slot.difficulty,
                    target_bloom=slot.bloom_level,
                    question_type=slot.question_type,
                    weak_topic_ids=self._ctx.weak_topic_ids,
                    already_selected=already_selected,
                )

                ranked = rank_candidates(
                    candidates,
                    criteria,
                    top_n=self._ctx.top_n_log,
                )

                asm.all_logged_candidates.extend(ranked)
                best = pick_best(ranked)

                if best:
                    asm.selected.append(best)
                    q_type = best.candidate.get("question_type", slot.question_type)
                    q_id = best.candidate.get("id", 0)
                    already_selected.add((q_type, q_id))

            assembled.append(asm)

        return assembled
