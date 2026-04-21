"""
Base rule contract for recommendation engine.
"""

from abc import ABC, abstractmethod
from typing import Sequence

from recommendation.models import AnalyticsSnapshot, CandidateRecommendation


class RecommendationRule(ABC):
    """
    Base interface for recommendation rules.

    Rules must only consume prepared `AnalyticsSnapshot` and must not issue SQL.
    """

    rule_id: str = "base_rule"
    priority: int = 100

    @abstractmethod
    async def evaluate(self, snapshot: AnalyticsSnapshot) -> Sequence[CandidateRecommendation]:
        """Return zero or more candidates."""

