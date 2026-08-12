"""
Recommendation Engine domain — Pure Domain Ranking Strategy (Phase 15 §4).

Strategy Pattern:
  - `RecommendationStrategy` is the abstract protocol.
  - `WeaknessPriorityStrategy` is the default production implementation.

Ranks topics/questions for practice recommendation using a composite score:
  score = (1.0 - mastery_score) * weakness_weight + recency_bonus + attempt_factor

Topics with lower mastery scores receive higher recommendation priority.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


class RecommendationStrategy(Protocol):
    """Strategy interface for topic/question recommendation ranking."""

    def rank_topics(
        self,
        candidate_topics: list[dict[str, Any]],
        weak_topic_ids: set[int],
    ) -> list[dict[str, Any]]:
        """
        Rank candidate topics by recommendation priority score (descending).

        Each candidate dict must contain:
          {"topic_id": int, "chapter_id": int, "subject_id": int, "mastery_score": float, "attempt_count": int}
        """
        ...


@dataclass(frozen=True)
class WeaknessPriorityStrategy:
    """
    Default recommendation strategy (§4.1).

    Priority Formula:
      priority_score = (1.0 - mastery_score) * 0.7 + (1.0 / (attempt_count + 1)) * 0.3

    Weak topics (mastery < 0.5) receive an additional +0.2 boost.
    """

    weakness_weight: float = 0.7
    attempt_weight: float = 0.3
    weak_topic_boost: float = 0.2

    def rank_topics(
        self,
        candidate_topics: list[dict[str, Any]],
        weak_topic_ids: set[int],
    ) -> list[dict[str, Any]]:
        ranked = []
        for cand in candidate_topics:
            mastery = float(cand.get("mastery_score", 0.0))
            attempts = int(cand.get("attempt_count", 0))
            topic_id = int(cand.get("topic_id", 0))

            base_score = (1.0 - mastery) * self.weakness_weight + (1.0 / (attempts + 1)) * self.attempt_weight
            if topic_id in weak_topic_ids:
                base_score += self.weak_topic_boost

            score = round(max(0.0, min(1.0, base_score)), 4)
            item = dict(cand)
            item["priority_score"] = score
            ranked.append(item)

        # Sort descending by priority_score
        ranked.sort(key=lambda x: x["priority_score"], reverse=True)
        return ranked


def determine_recommended_difficulty(avg_mastery: float) -> str:
    """
    Determine recommended difficulty based on student's average mastery score:
      - mastery < 0.4  → EASY (build confidence)
      - 0.4 <= mastery < 0.75 → MEDIUM (solidify skills)
      - mastery >= 0.75 → HARD (challenge mastery)
    """
    if avg_mastery < 0.4:
        return "EASY"
    elif avg_mastery < 0.75:
        return "MEDIUM"
    else:
        return "HARD"
