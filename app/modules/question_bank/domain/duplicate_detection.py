"""
Question Bank duplicate detection engine.

Implements exact matching and fuzzy token similarity matching (RapidFuzz with difflib fallback),
strictly scoped by (board_id, subject_id, primary_chapter_id).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

try:
    import rapidfuzz
    HAS_RAPIDFUZZ = True
except ImportError:
    import difflib
    HAS_RAPIDFUZZ = False


@dataclass
class DuplicateResult:
    """Result of duplicate check analysis."""

    is_duplicate: bool
    match_type: str | None = None  # "EXACT" | "FUZZY"
    score: float = 0.0
    matched_question_id: int | None = None
    matched_question_public_id: str | None = None


def normalize_text(text: str) -> str:
    """Normalize text by lowercasing, stripping punctuation, and compressing whitespace."""
    if not text:
        return ""
    text = text.lower()
    text = re.sub(r"[^\w\s]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def calculate_similarity(text1: str, text2: str) -> float:
    """Calculate token similarity score between 0.0 and 100.0."""
    norm1 = normalize_text(text1)
    norm2 = normalize_text(text2)

    if norm1 == norm2:
        return 100.0

    if HAS_RAPIDFUZZ:
        return float(rapidfuzz.fuzz.token_sort_ratio(norm1, norm2))
    else:
        matcher = difflib.SequenceMatcher(None, norm1, norm2)
        return round(matcher.ratio() * 100.0, 2)


def check_duplicate_candidate(
    new_text: str,
    candidates: list[dict[str, Any]],
    threshold: float = 90.0,
) -> DuplicateResult:
    """
    Checks candidate questions in the same academic scope for duplicates.
    Returns DuplicateResult indicating exact or fuzzy match.
    """
    norm_new = normalize_text(new_text)

    # 1. Exact match check
    for candidate in candidates:
        cand_text = candidate.get("question_text") or candidate.get("question_text_with_blanks") or ""
        norm_cand = normalize_text(cand_text)

        if norm_new == norm_cand:
            return DuplicateResult(
                is_duplicate=True,
                match_type="EXACT",
                score=100.0,
                matched_question_id=candidate.get("id"),
                matched_question_public_id=str(candidate.get("public_id", "")),
            )

    # 2. Fuzzy match check
    for candidate in candidates:
        cand_text = candidate.get("question_text") or candidate.get("question_text_with_blanks") or ""
        score = calculate_similarity(new_text, cand_text)

        if score >= threshold:
            return DuplicateResult(
                is_duplicate=True,
                match_type="FUZZY",
                score=score,
                matched_question_id=candidate.get("id"),
                matched_question_public_id=str(candidate.get("public_id", "")),
            )

    return DuplicateResult(is_duplicate=False)
