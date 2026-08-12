"""
Paper Generation domain — Validation Rules (Phase 11 §6.8 & §13).

Pure functions: each rule takes the paper state and blueprint, returns a
ValidationResult. No DB calls — all data pre-fetched by the service before
calling these functions.

Rule codes (8 rules per spec):
  TOTAL_MARKS_MATCH       — paper total_marks == blueprint total_marks
  DURATION_VALID          — blueprint duration_minutes > 0
  SECTION_MARKS_MATCH     — each section's actual marks == blueprint section_marks
  DIFFICULTY_BALANCE      — per-section difficulty mix within ±10% of targets
  BLOOM_COVERAGE          — bloom_distribution targets met (if specified)
  NO_DUPLICATE_QUESTIONS  — no question_id appears twice in same paper
  CHAPTER_COVERAGE        — selected questions cover required chapters
  QUESTION_AVAILABILITY   — every section has enough questions to fill its slots
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ValidationResult:
    """Result for a single validation rule."""

    rule_code: str
    passed: bool
    detail: str | None = None


# ---------------------------------------------------------------------------
# Individual rule implementations
# ---------------------------------------------------------------------------

def _rule_total_marks_match(
    paper_total: float,
    blueprint_total: float,
) -> ValidationResult:
    passed = abs(paper_total - blueprint_total) < 0.01
    detail = (
        None
        if passed
        else f"Paper total {paper_total} ≠ blueprint total {blueprint_total}"
    )
    return ValidationResult("TOTAL_MARKS_MATCH", passed, detail)


def _rule_duration_valid(duration_minutes: int) -> ValidationResult:
    passed = duration_minutes > 0
    detail = None if passed else "Blueprint duration_minutes must be > 0"
    return ValidationResult("DURATION_VALID", passed, detail)


def _rule_section_marks_match(
    sections: list[dict[str, Any]],
    blueprint_sections: list[dict[str, Any]],
) -> ValidationResult:
    """Each paper section's total question marks must equal its blueprint rule."""
    mismatches: list[str] = []
    bp_map = {s["section_label"]: s["section_marks"] for s in blueprint_sections}

    for sec in sections:
        label = sec["section_label"]
        actual = sec.get("actual_marks", sec.get("section_marks", 0.0))
        expected = bp_map.get(label)
        if expected is not None and abs(actual - expected) > 0.01:
            mismatches.append(f"{label}: got {actual}, expected {expected}")

    passed = not mismatches
    return ValidationResult(
        "SECTION_MARKS_MATCH",
        passed,
        "; ".join(mismatches) if mismatches else None,
    )


def _rule_difficulty_balance(
    sections: list[dict[str, Any]],
    blueprint_sections: list[dict[str, Any]],
    tolerance_pct: float = 10.0,
) -> ValidationResult:
    """
    Actual difficulty distribution per section must be within ±tolerance_pct
    of the blueprint target distribution.
    """
    bp_map = {s["section_label"]: s for s in blueprint_sections}
    violations: list[str] = []

    for sec in sections:
        label = sec["section_label"]
        bp_sec = bp_map.get(label)
        if not bp_sec:
            continue
        target_dist: dict = bp_sec.get("difficulty_distribution_json", {})
        actual_dist: dict = sec.get("actual_difficulty_distribution", {})
        if not target_dist or not actual_dist:
            continue

        for diff, target_pct in target_dist.items():
            actual_pct = actual_dist.get(diff, 0)
            if abs(actual_pct - target_pct) > tolerance_pct:
                violations.append(
                    f"{label}/{diff}: target={target_pct}%, actual={actual_pct}%"
                )

    passed = not violations
    return ValidationResult(
        "DIFFICULTY_BALANCE",
        passed,
        "; ".join(violations) if violations else None,
    )


def _rule_bloom_coverage(
    sections: list[dict[str, Any]],
    blueprint_sections: list[dict[str, Any]],
    tolerance_pct: float = 15.0,
) -> ValidationResult:
    """Bloom distribution targets (if specified) must be within ±tolerance_pct."""
    bp_map = {s["section_label"]: s for s in blueprint_sections}
    violations: list[str] = []

    for sec in sections:
        label = sec["section_label"]
        bp_sec = bp_map.get(label)
        if not bp_sec:
            continue
        target_bloom: dict | None = bp_sec.get("bloom_distribution_json")
        if not target_bloom:
            continue
        actual_bloom: dict = sec.get("actual_bloom_distribution", {})

        for level, target_pct in target_bloom.items():
            actual_pct = actual_bloom.get(level, 0)
            if abs(actual_pct - target_pct) > tolerance_pct:
                violations.append(
                    f"{label}/{level}: target={target_pct}%, actual={actual_pct}%"
                )

    passed = not violations
    return ValidationResult(
        "BLOOM_COVERAGE",
        passed,
        "; ".join(violations) if violations else None,
    )


def _rule_no_duplicate_questions(
    paper_questions: list[dict[str, Any]],
) -> ValidationResult:
    """No (question_type, question_id) pair may appear twice in the same paper."""
    seen: set[tuple[str, int]] = set()
    duplicates: list[str] = []

    for q in paper_questions:
        key = (q["question_type"], q["question_id"])
        if key in seen:
            duplicates.append(f"{key[0]}:{key[1]}")
        seen.add(key)

    passed = not duplicates
    return ValidationResult(
        "NO_DUPLICATE_QUESTIONS",
        passed,
        f"Duplicate questions: {', '.join(duplicates)}" if duplicates else None,
    )


def _rule_chapter_coverage(
    paper_questions: list[dict[str, Any]],
    required_chapter_ids: list[int],
) -> ValidationResult:
    """All required chapters must have at least one question selected."""
    if not required_chapter_ids:
        return ValidationResult("CHAPTER_COVERAGE", True)

    covered = {q.get("primary_chapter_id") for q in paper_questions}
    missing = [c for c in required_chapter_ids if c not in covered]

    passed = not missing
    return ValidationResult(
        "CHAPTER_COVERAGE",
        passed,
        f"Missing chapters: {missing}" if missing else None,
    )


def _rule_question_availability(
    sections: list[dict[str, Any]],
) -> ValidationResult:
    """
    Every section must have filled all its required question slots.
    A section's 'filled_count' must equal its 'required_count'.
    """
    short: list[str] = []
    for sec in sections:
        label = sec["section_label"]
        filled = sec.get("filled_count", 0)
        required = sec.get("required_count", 0)
        if filled < required:
            short.append(f"{label}: need {required}, got {filled}")

    passed = not short
    return ValidationResult(
        "QUESTION_AVAILABILITY",
        passed,
        "; ".join(short) if short else None,
    )


# ---------------------------------------------------------------------------
# Orchestrator — run all 8 rules, return list of results
# ---------------------------------------------------------------------------

def run_all_validations(
    paper_total: float,
    blueprint_total: float,
    blueprint_duration: int,
    sections: list[dict[str, Any]],
    blueprint_sections: list[dict[str, Any]],
    paper_questions: list[dict[str, Any]],
    required_chapter_ids: list[int] | None = None,
) -> list[ValidationResult]:
    """
    Run all 8 validation rules and return one ValidationResult per rule.

    Caller passes pre-computed dicts so this function stays pure and testable.
    """
    return [
        _rule_total_marks_match(paper_total, blueprint_total),
        _rule_duration_valid(blueprint_duration),
        _rule_section_marks_match(sections, blueprint_sections),
        _rule_difficulty_balance(sections, blueprint_sections),
        _rule_bloom_coverage(sections, blueprint_sections),
        _rule_no_duplicate_questions(paper_questions),
        _rule_chapter_coverage(paper_questions, required_chapter_ids or []),
        _rule_question_availability(sections),
    ]


def all_passed(results: list[ValidationResult]) -> bool:
    """True only when every validation rule passed."""
    return all(r.passed for r in results)
