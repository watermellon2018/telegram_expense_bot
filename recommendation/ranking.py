"""
Ranking layer for recommendation candidates.
"""

from abc import ABC, abstractmethod
from typing import List, Sequence

from recommendation.models import CandidateRecommendation, RecommendationSettings


class RankingService(ABC):
    """Ranks and filters rule candidates."""

    @abstractmethod
    def rank(
        self,
        candidates: Sequence[CandidateRecommendation],
        settings: RecommendationSettings,
    ) -> Sequence[CandidateRecommendation]:
        """Return ranked candidates."""


class ScoreRankingService(RankingService):
    """Sort by score DESC then priority ASC, apply global limits."""

    def rank(
        self,
        candidates: Sequence[CandidateRecommendation],
        settings: RecommendationSettings,
    ) -> Sequence[CandidateRecommendation]:
        filtered: List[CandidateRecommendation] = [
            item for item in candidates if item.score >= settings.min_score
        ]
        filtered.sort(key=lambda item: (-item.score, item.priority, item.rule_id))
        return filtered[: settings.max_recommendations]

