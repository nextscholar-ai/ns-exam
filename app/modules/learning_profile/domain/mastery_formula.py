"""
Mastery Engine domain — Mastery Formula Strategy (Phase 14 §4).

Implements the Exponential Moving Average (EMA) mastery update formula.

Strategy Pattern:
  - `MasteryFormula` is the abstract protocol.
  - `EMAMasteryFormula` is the default production implementation.
  - Swap formula by injecting a different strategy into MasteryService.

EMA Formula:
  new_mastery = α × question_score + (1 − α) × current_mastery

Where:
  - α (alpha) = smoothing factor in (0, 1].
  - Smaller α = slower change (more weight on history).
  - Larger α = faster change (more weight on latest result).
  - Default α = 0.3 (standard adaptive learning EMA).

Boundaries:
  - mastery_score is always clamped to [0.0, 1.0].
  - question_score = marks_obtained / max_marks (0.0–1.0).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class MasteryFormula(Protocol):
    """Strategy interface for mastery update algorithms."""

    def compute(
        self,
        current_mastery: float,
        question_score: float,
        attempt_count: int,
    ) -> tuple[float, float]:
        """
        Compute new mastery score.

        Args:
            current_mastery: Existing mastery score (0.0–1.0).
            question_score: Raw score for this question (0.0–1.0).
            attempt_count: Number of prior attempts (used for adaptive alpha).

        Returns:
            Tuple of (new_mastery, alpha_used).
        """
        ...


@dataclass(frozen=True)
class EMAMasteryFormula:
    """
    Exponential Moving Average mastery update (§4.1).

    Uses adaptive alpha that starts high (0.5) for the first few attempts
    (quick initial calibration) and converges to base_alpha over time.

    Adaptive schedule:
      - attempt 1: alpha = 0.5   (first impression heavily weighted)
      - attempt 2: alpha = 0.4
      - attempt 3+: alpha = base_alpha (default 0.3)
    """

    base_alpha: float = 0.3

    # Adaptive alpha schedule indexed by attempt_count (0-indexed).
    # attempt_count here is BEFORE the current update.
    ADAPTIVE_ALPHA: tuple[float, ...] = (0.5, 0.4)

    def compute(
        self,
        current_mastery: float,
        question_score: float,
        attempt_count: int,
    ) -> tuple[float, float]:
        """Return (new_mastery, alpha_used)."""
        # Select alpha adaptively
        if attempt_count < len(self.ADAPTIVE_ALPHA):
            alpha = self.ADAPTIVE_ALPHA[attempt_count]
        else:
            alpha = self.base_alpha

        new_mastery = alpha * question_score + (1.0 - alpha) * current_mastery
        # Clamp to valid range
        new_mastery = max(0.0, min(1.0, new_mastery))
        return round(new_mastery, 4), round(alpha, 3)


def compute_question_score(marks_obtained: float, max_marks: float) -> float:
    """
    Normalize marks_obtained to a [0.0, 1.0] question score.

    Returns 0.0 if max_marks is 0 to avoid division by zero.
    """
    if max_marks <= 0:
        return 0.0
    return round(max(0.0, min(1.0, marks_obtained / max_marks)), 4)


def aggregate_mastery(scores: list[float]) -> float:
    """
    Compute simple average of mastery scores for chapter/subject aggregation.
    Returns 0.0 for empty list.
    """
    if not scores:
        return 0.0
    return round(sum(scores) / len(scores), 4)
