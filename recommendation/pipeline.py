"""
End-to-end recommendation pipeline orchestration.
"""

from typing import List, Optional, Sequence

from recommendation.analytics import AnalyticsService, PreparedAnalyticsService
from recommendation.formatter import DefaultRecommendationFormatter, RecommendationFormatter
from recommendation.models import (
    FinalRecommendation,
    RecommendationFeedback,
    RecommendationHistoryEntry,
    RecommendationRequest,
    RecommendationSettings,
)
from recommendation.outliers import BaselineOutlierHandler, OutlierHandler
from recommendation.ranking import RankingService, ScoreRankingService
from recommendation.repositories.in_memory import (
    InMemoryFeedbackRepository,
    InMemoryHistoryRepository,
    InMemorySettingsRepository,
)
from recommendation.repositories.interfaces import FeedbackRepository, HistoryRepository, SettingsRepository
from recommendation.rule_engine import DefaultRuleEngine, RuleEngine
from recommendation.rules.base import RecommendationRule


class RecommendationPipeline:
    """Orchestrates all recommendation module layers."""

    def __init__(
        self,
        analytics_service: AnalyticsService,
        outlier_handler: OutlierHandler,
        rule_engine: RuleEngine,
        ranking_service: RankingService,
        formatter: RecommendationFormatter,
        settings_repository: SettingsRepository,
        history_repository: HistoryRepository,
        feedback_repository: FeedbackRepository,
    ):
        self._analytics_service = analytics_service
        self._outlier_handler = outlier_handler
        self._rule_engine = rule_engine
        self._ranking_service = ranking_service
        self._formatter = formatter
        self._settings_repository = settings_repository
        self._history_repository = history_repository
        self._feedback_repository = feedback_repository

    async def generate(self, request: RecommendationRequest) -> Sequence[FinalRecommendation]:
        """
        Generate ranked and formatted recommendations for request.

        Rules receive only prepared `AnalyticsSnapshot` from analytics layer.
        """
        settings = await self._settings_repository.get_settings(request.user_id, request.project_id)
        if not settings.enabled:
            return []

        snapshot = await self._analytics_service.build_snapshot(request)
        adjusted_snapshot = await self._outlier_handler.adjust(snapshot)

        candidates = await self._rule_engine.evaluate(adjusted_snapshot, settings)
        ranked = self._ranking_service.rank(candidates, settings)
        final_recommendations = self._formatter.format(ranked, adjusted_snapshot)

        if final_recommendations:
            history_entries = self._to_history_entries(
                request=request,
                recommendations=final_recommendations,
            )
            persisted = await self._history_repository.insert_generated(history_entries)
            history_ids = [item.id for item in persisted if item.id is not None]
            if history_ids:
                await self._history_repository.mark_as_shown(history_ids)

        return final_recommendations

    async def get_settings(self, user_id: str, project_id: Optional[int]) -> RecommendationSettings:
        """Expose settings lookup for callers that need module config."""
        return await self._settings_repository.get_settings(user_id, project_id)

    async def save_feedback(self, feedback: RecommendationFeedback) -> RecommendationFeedback:
        """Store user feedback through repository layer."""
        return await self._feedback_repository.save_feedback(feedback)

    @staticmethod
    def _to_history_entries(
        request: RecommendationRequest,
        recommendations: Sequence[FinalRecommendation],
    ) -> Sequence[RecommendationHistoryEntry]:
        period_key = RecommendationPipeline._resolve_period_key(request)
        entries: List[RecommendationHistoryEntry] = []
        for item in recommendations:
            payload = {
                "recommendation_id": item.recommendation_id,
                "source_rule_id": item.source_rule_id,
                "project_id": request.project_id,
                "rank": item.rank,
                **dict(item.payload),
            }
            entries.append(
                RecommendationHistoryEntry(
                    id=None,
                    user_id=request.user_id,
                    recommendation_type=item.recommendation_type,
                    period_key=period_key,
                    entity_type=item.payload.get("entity_type"),
                    entity_id=(
                        str(item.payload.get("entity_id"))
                        if item.payload.get("entity_id") is not None
                        else None
                    ),
                    payload_json=payload,
                    score=item.score,
                    generated_at=request.requested_at,
                )
            )
        return entries

    @staticmethod
    def _resolve_period_key(request: RecommendationRequest) -> str:
        custom_period_key = request.metadata.get("period_key")
        if custom_period_key:
            return str(custom_period_key)

        if request.period_start and request.period_end:
            return f"{request.period_start.isoformat()}:{request.period_end.isoformat()}"

        if request.period_start:
            return request.period_start.strftime("%Y-%m")

        return request.requested_at.strftime("%Y-%m")


def build_default_recommendation_pipeline(
    rules: Sequence[RecommendationRule],
) -> RecommendationPipeline:
    """
    Build default recommendation pipeline skeleton.

    Repository implementations are intentionally in-memory for now.
    They can be replaced by PostgreSQL implementations without touching rules.
    """
    return RecommendationPipeline(
        analytics_service=PreparedAnalyticsService(),
        outlier_handler=BaselineOutlierHandler(),
        rule_engine=DefaultRuleEngine(rules),
        ranking_service=ScoreRankingService(),
        formatter=DefaultRecommendationFormatter(),
        settings_repository=InMemorySettingsRepository(),
        history_repository=InMemoryHistoryRepository(),
        feedback_repository=InMemoryFeedbackRepository(),
    )
