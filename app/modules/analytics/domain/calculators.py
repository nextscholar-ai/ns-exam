"""
Analytics Engine domain — Pure Domain Calculators (Phase 16 §4).

Pure mathematical domain functions for:
  - `compute_trend_direction`: Evaluates slope from chronological mastery scores.
  - `evaluate_student_risk`: Identifies at-risk students based on mastery & failed exams.
  - `compute_pass_percentage`: Calculates pass rate percentage.
"""
from __future__ import annotations


def compute_trend_direction(mastery_history_scores: list[float]) -> str:
    """
    Determine trend direction from a list of chronological mastery scores:
      - Slope > +0.05  → IMPROVING
      - Slope < -0.05  → DECLINING
      - Otherwise       → STABLE
    """
    if len(mastery_history_scores) < 2:
        return "STABLE"

    first_half = mastery_history_scores[: len(mastery_history_scores) // 2]
    second_half = mastery_history_scores[len(mastery_history_scores) // 2 :]

    avg_first = sum(first_half) / len(first_half) if first_half else 0.0
    avg_second = sum(second_half) / len(second_half) if second_half else 0.0

    delta = avg_second - avg_first

    if delta > 0.05:
        return "IMPROVING"
    elif delta < -0.05:
        return "DECLINING"
    else:
        return "STABLE"


def evaluate_student_risk(
    overall_mastery: float,
    failed_exams_count: int,
    trend_direction: str,
) -> tuple[bool, list[str]]:
    """
    Evaluate if a student is at risk:
      - overall_mastery < 0.40  → Risk: Low overall topic mastery.
      - failed_exams_count >= 2 → Risk: Multiple exam failures.
      - trend_direction == DECLINING and overall_mastery < 0.50 → Risk: Declining mastery.

    Returns:
      Tuple of (is_at_risk, list_of_risk_reasons).
    """
    reasons: list[str] = []

    if overall_mastery < 0.40:
        reasons.append("Overall mastery is critically low (< 40%)")

    if failed_exams_count >= 2:
        reasons.append(f"Failed {failed_exams_count} exams")

    if trend_direction == "DECLINING" and overall_mastery < 0.50:
        reasons.append("Performance trend is declining below 50% threshold")

    return len(reasons) > 0, reasons


def compute_pass_percentage(passed_count: int, total_count: int) -> float:
    """Calculate pass percentage rounded to 2 decimals."""
    if total_count <= 0:
        return 0.0
    return round((passed_count / total_count) * 100.0, 2)
