"""
Analytics layer for recommendation module.
"""

from abc import ABC, abstractmethod
from typing import Dict

from recommendation.models import AnalyticsSnapshot, RecommendationRequest


class AnalyticsService(ABC):
    """Builds prepared analytics snapshots for downstream layers."""

    @abstractmethod
    async def build_snapshot(self, request: RecommendationRequest) -> AnalyticsSnapshot:
        """Convert raw/prepared inputs into analytics snapshot."""


class PreparedAnalyticsService(AnalyticsService):
    """
    Default analytics service.

    This service does not read DB directly; it only converts prepared input
    payload into a normalized snapshot for rules.
    """

    async def build_snapshot(self, request: RecommendationRequest) -> AnalyticsSnapshot:
        metrics: Dict[str, float] = dict(request.metrics)
        return AnalyticsSnapshot(
            user_id=request.user_id,
            project_id=request.project_id,
            generated_at=request.requested_at,
            period_start=request.period_start,
            period_end=request.period_end,
            metrics=metrics,
            dimensions=dict(request.dimensions),
            events=tuple(request.events),
            baseline_metrics=metrics,
            metadata=dict(request.metadata),
        )

