"""
OMR Detection — Bubble Detection Engine (Phase 13 §7).

Measures fill-ratio per option, computes sheet-wide confidence score, and flags
low-confidence or ambiguous questions for manual review.

Pure functions — no DB dependencies.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class BubbleDetectionResult:
    detected_answers: dict[str, str]           # {"1": "A", "2": "C"}
    confidence_score: float                   # Overall sheet average 0.0 - 100.0
    low_confidence_questions: list[dict[str, Any]]  # Flagged items requiring review
    detected_grid: dict[str, Any]


def detect_bubbles_from_matrix(
    raw_bubble_fills: dict[str, dict[str, float]],
    fill_threshold: float = 0.5,
    ambiguity_margin: float = 0.15,
) -> BubbleDetectionResult:
    """
    Evaluates raw bubble fill ratios per question number.

    raw_bubble_fills structure:
      {
        "1": {"A": 0.92, "B": 0.05, "C": 0.02, "D": 0.01},
        "2": {"A": 0.40, "B": 0.45, "C": 0.01, "D": 0.00},
      }
    """
    detected_answers: dict[str, str] = {}
    low_confidence: list[dict[str, Any]] = []
    confidence_scores: list[float] = []

    for q_num, options in raw_bubble_fills.items():
        sorted_opts = sorted(options.items(), key=lambda item: item[1], reverse=True)
        best_opt, best_val = sorted_opts[0]
        second_val = sorted_opts[1][1] if len(sorted_opts) > 1 else 0.0

        if best_val < fill_threshold:
            # Low fill or blank bubble
            confidence_scores.append(best_val * 100.0)
            low_confidence.append(
                {
                    "question_num": q_num,
                    "reason": "BLANK_OR_LOW_FILL",
                    "top_fill": best_val,
                }
            )
        elif (best_val - second_val) < ambiguity_margin and second_val >= (fill_threshold * 0.7):
            # Ambiguous multiple filled bubbles
            confidence_scores.append(50.0)
            low_confidence.append(
                {
                    "question_num": q_num,
                    "reason": "MULTIPLE_BUBBLES_FILLED",
                    "top_fill": best_val,
                    "second_fill": second_val,
                }
            )
            detected_answers[q_num] = best_opt
        else:
            confidence_scores.append(min(100.0, best_val * 100.0))
            detected_answers[q_num] = best_opt

    avg_conf = (
        round(sum(confidence_scores) / len(confidence_scores), 2)
        if confidence_scores
        else 0.0
    )

    return BubbleDetectionResult(
        detected_answers=detected_answers,
        confidence_score=avg_conf,
        low_confidence_questions=low_confidence,
        detected_grid={"total_questions": len(raw_bubble_fills)},
    )
