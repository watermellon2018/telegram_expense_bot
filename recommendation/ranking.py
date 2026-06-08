"""
Ranking layer for recommendation candidates.
"""

from abc import ABC, abstractmethod
from dataclasses import replace
from datetime import datetime
from typing import List, Mapping, Optional, Sequence

from recommendation.models import (
    AnalyticsSnapshot,
    CandidateRecommendation,
    RecommendationRecord,
    RecommendationSettings,
)
from recommendation.types import RecommendationType


class RankingService(ABC):
    """Ranks and filters rule candidates."""

    @abstractmethod
    def rank(
        self,
        candidates: Sequence[CandidateRecommendation],
        settings: RecommendationSettings,
        snapshot: AnalyticsSnapshot,
        recent_history: Sequence[RecommendationRecord] = tuple(),
    ) -> Sequence[CandidateRecommendation]:
        """Return ranked candidates."""


class ScoreRankingService(RankingService):
    """Deterministic scoring, novelty penalty, deduplication, and top-N selection."""

    _BASE_PRIORITY = {
        RecommendationType.FORECAST_OVERSPEND: 34.0,
        RecommendationType.TOTAL_GROWTH_VS_PREV_MONTH: 30.0,
        RecommendationType.TOTAL_GROWTH_VS_3M_BASELINE: 28.0,
        RecommendationType.CATEGORY_GROWTH_VS_PREV_MONTH: 26.0,
        RecommendationType.CATEGORY_GROWTH_VS_3M_BASELINE: 24.0,
        RecommendationType.HIGH_RECURRING_SHARE: 24.0,
        RecommendationType.RECURRING_REVIEW: 22.0,
        RecommendationType.SMALL_EXPENSES_ACCUMULATION: 22.0,
        RecommendationType.CASHBACK_OPPORTUNITY: 20.0,
        RecommendationType.WEEKDAY_SPENDING_PATTERN: 18.0,
        RecommendationType.POSITIVE_CATEGORY_REDUCTION: 16.0,
    }

    _SIMILAR_GROUP = {
        RecommendationType.FORECAST_OVERSPEND: "growth_family",
        RecommendationType.TOTAL_GROWTH_VS_PREV_MONTH: "growth_family",
        RecommendationType.TOTAL_GROWTH_VS_3M_BASELINE: "growth_family",
        RecommendationType.HIGH_RECURRING_SHARE: "recurring_family",
        RecommendationType.RECURRING_REVIEW: "recurring_family",
    }

    def rank(
        self,
        candidates: Sequence[CandidateRecommendation],
        settings: RecommendationSettings,
        snapshot: AnalyticsSnapshot,
        recent_history: Sequence[RecommendationRecord] = tuple(),
    ) -> Sequence[CandidateRecommendation]:
        if not candidates:
            return []

        rescored: List[CandidateRecommendation] = []
        for candidate in candidates:
            if candidate.recommendation_type in settings.hidden_recommendation_types:
                continue
            if (
                not settings.show_positive_recommendations
                and candidate.recommendation_type == RecommendationType.POSITIVE_CATEGORY_REDUCTION
            ):
                continue
            if (
                settings.min_score <= 1.0
                and candidate.score <= 1.0
                and candidate.score < settings.min_score
            ):
                continue

            final_score = self._compute_final_score(
                candidate=candidate,
                snapshot=snapshot,
                recent_history=recent_history,
            )
            if settings.min_score > 1.0 and final_score < settings.min_score:
                continue
            rescored.append(replace(candidate, score=round(final_score, 4)))

        if not rescored:
            return []

        rescored.sort(key=lambda item: (-item.score, item.priority, item.rule_id))
        deduplicated = self._deduplicate(rescored)
        return deduplicated[: settings.max_recommendations]

    def _compute_final_score(
        self,
        candidate: CandidateRecommendation,
        snapshot: AnalyticsSnapshot,
        recent_history: Sequence[RecommendationRecord],
    ) -> float:
        base_priority = self._BASE_PRIORITY.get(candidate.recommendation_type, 20.0)
        severity = self._severity_score(candidate)
        impact = self._impact_score(candidate)
        confidence = self._confidence_score(snapshot)
        novelty_penalty = self._novelty_penalty(
            candidate=candidate,
            recent_history=recent_history,
            now=snapshot.generated_at,
        )
        return max(0.0, base_priority + severity + impact + confidence - novelty_penalty)

    def _severity_score(self, candidate: CandidateRecommendation) -> float:
        payload = candidate.payload
        percent = self._first_number(
            payload,
            (
                "overspend_pct",
                "delta_pct",
                "reduction_share",
                "category_share",
                "recurring_share",
                "small_share",
                "ratio",
            ),
        )
        if percent is None:
            percent = candidate.score

        if percent <= 1.0:
            percent *= 100.0
        return min(25.0, max(0.0, percent) * 0.25)

    def _impact_score(self, candidate: CandidateRecommendation) -> float:
        payload = candidate.payload
        amount = self._first_number(
            payload,
            (
                "overspend_amount",
                "delta_amount",
                "category_amount",
                "recurring_amount",
                "small_amount",
                "weekend_spend",
                "estimated_cashback",
            ),
        )
        if amount is None:
            return 0.0
        return min(20.0, max(0.0, amount) / 100.0)

    def _confidence_score(self, snapshot: AnalyticsSnapshot) -> float:
        tx_count = self._metric(snapshot, "tx_count")
        tx_factor = min(1.0, tx_count / 25.0)

        full_total = self._metric(snapshot, "total_expense_full")
        adjusted_total = self._metric(snapshot, "total_expense_baseline_adjusted")
        if full_total <= 0:
            distortion_ratio = 0.0
        else:
            distortion_ratio = abs(full_total - adjusted_total) / full_total
        outlier_factor = max(0.0, 1.0 - (distortion_ratio * 1.5))

        return ((tx_factor * 0.7) + (outlier_factor * 0.3)) * 15.0

    def _novelty_penalty(
        self,
        candidate: CandidateRecommendation,
        recent_history: Sequence[RecommendationRecord],
        now: datetime,
    ) -> float:
        if not recent_history:
            return 0.0

        candidate_entity_id = self._entity_id(candidate)
        penalty = 0.0
        for record in recent_history:
            if record.recommendation_type != candidate.recommendation_type:
                continue

            age_days = max(0, (now - record.presented_at).days)
            if age_days <= 7:
                weight = 1.0
            elif age_days <= 30:
                weight = 0.6
            else:
                weight = 0.3

            penalty += 4.0 * weight
            if candidate_entity_id and candidate_entity_id == self._entity_id_from_payload(record.payload):
                penalty += 3.0 * weight

        return min(25.0, penalty)

    def _deduplicate(
        self,
        candidates: Sequence[CandidateRecommendation],
    ) -> List[CandidateRecommendation]:
        result: List[CandidateRecommendation] = []
        seen_categories = set()
        seen_similarity_groups = set()

        for candidate in candidates:
            entity_type = str(candidate.payload.get("entity_type") or "")
            entity_id = self._entity_id(candidate)
            if entity_type == "category" and entity_id:
                if entity_id in seen_categories:
                    continue
                seen_categories.add(entity_id)

            group = self._similarity_group(candidate)
            if group in seen_similarity_groups:
                continue
            seen_similarity_groups.add(group)
            result.append(candidate)

        return result

    def _similarity_group(self, candidate: CandidateRecommendation) -> str:
        mapped = self._SIMILAR_GROUP.get(candidate.recommendation_type)
        if mapped is not None:
            return mapped

        if candidate.recommendation_type in {
            RecommendationType.CATEGORY_GROWTH_VS_PREV_MONTH,
            RecommendationType.CATEGORY_GROWTH_VS_3M_BASELINE,
        }:
            entity_id = self._entity_id(candidate)
            if entity_id:
                return "category_growth:" + entity_id
            return "category_growth:any"

        return "type:" + candidate.recommendation_type.value

    @staticmethod
    def _entity_id(candidate: CandidateRecommendation) -> str:
        return ScoreRankingService._entity_id_from_payload(candidate.payload)

    @staticmethod
    def _entity_id_from_payload(payload: Mapping[str, object]) -> str:
        value = payload.get("entity_id")
        if value is None:
            return ""
        return str(value)

    @staticmethod
    def _first_number(
        payload: Mapping[str, object],
        keys: Sequence[str],
    ) -> Optional[float]:
        for key in keys:
            value = payload.get(key)
            if value is None:
                continue
            try:
                return float(value)
            except (TypeError, ValueError):
                continue
        return None

    @staticmethod
    def _metric(snapshot: AnalyticsSnapshot, key: str) -> float:
        value = snapshot.metrics.get(key, 0.0)
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0
