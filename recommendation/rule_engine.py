"""
Rule engine layer.
"""

from abc import ABC, abstractmethod
from dataclasses import replace
from typing import List, Sequence

from recommendation.models import AnalyticsSnapshot, CandidateRecommendation, RecommendationSettings
from recommendation.rules.base import RecommendationRule


class RuleEngine(ABC):
    """Executes recommendation rules over prepared analytics snapshot."""

    @abstractmethod
    async def evaluate(
        self,
        snapshot: AnalyticsSnapshot,
        settings: RecommendationSettings,
    ) -> Sequence[CandidateRecommendation]:
        """Return candidates produced by enabled rules."""


class DefaultRuleEngine(RuleEngine):
    """Default sequential rule engine."""

    def __init__(self, rules: Sequence[RecommendationRule]):
        self._rules = list(rules)

    async def evaluate(
        self,
        snapshot: AnalyticsSnapshot,
        settings: RecommendationSettings,
    ) -> Sequence[CandidateRecommendation]:
        candidates: List[CandidateRecommendation] = []

        for rule in sorted(self._rules, key=lambda item: item.priority):
            if not settings.rule_overrides.get(rule.rule_id, True):
                continue

            rule_candidates = await rule.evaluate(snapshot)
            for candidate in rule_candidates:
                if candidate.rule_id:
                    candidates.append(candidate)
                    continue

                candidates.append(replace(candidate, rule_id=rule.rule_id))

        return candidates

