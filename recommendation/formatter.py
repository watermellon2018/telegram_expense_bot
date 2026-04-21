"""
Presentation/formatter layer for recommendations.
"""

from abc import ABC, abstractmethod
from typing import List, Sequence
from uuid import uuid4

from recommendation.models import AnalyticsSnapshot, CandidateRecommendation, FinalRecommendation


class RecommendationFormatter(ABC):
    """Formats ranked candidates to final presentation objects."""

    @abstractmethod
    def format(
        self,
        ranked_candidates: Sequence[CandidateRecommendation],
        snapshot: AnalyticsSnapshot,
    ) -> Sequence[FinalRecommendation]:
        """Return final recommendations."""


class DefaultRecommendationFormatter(RecommendationFormatter):
    """Simple formatter that builds message text from title/rationale/actions."""

    def format(
        self,
        ranked_candidates: Sequence[CandidateRecommendation],
        snapshot: AnalyticsSnapshot,
    ) -> Sequence[FinalRecommendation]:
        results: List[FinalRecommendation] = []

        for index, candidate in enumerate(ranked_candidates, start=1):
            actions_line = ""
            if candidate.actions:
                actions_line = "\nДействия: " + ", ".join(candidate.actions)

            results.append(
                FinalRecommendation(
                    recommendation_id=str(uuid4()),
                    source_rule_id=candidate.rule_id,
                    recommendation_type=candidate.recommendation_type,
                    title=candidate.title,
                    message=candidate.rationale + actions_line,
                    score=candidate.score,
                    rank=index,
                    actions=tuple(candidate.actions),
                    payload=dict(candidate.payload),
                )
            )

        return results

