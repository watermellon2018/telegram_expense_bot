"""
Service layer for recommendation feedback events.
"""

from datetime import datetime
from typing import Mapping, Optional, Sequence

from recommendation.models import RecommendationFeedback
from recommendation.repositories.interfaces import FeedbackRepository
from recommendation.types import RecommendationFeedbackActionType


class RecommendationFeedbackService:
    """Facade for writing and reading recommendation feedback events."""

    def __init__(self, repository: FeedbackRepository):
        self._repository = repository

    async def add_feedback_event(
        self,
        recommendation_id: str,
        user_id: str,
        action_type: RecommendationFeedbackActionType,
        metadata_json: Optional[Mapping[str, object]] = None,
        created_at: Optional[datetime] = None,
    ) -> RecommendationFeedback:
        event = RecommendationFeedback(
            recommendation_id=recommendation_id,
            user_id=user_id,
            action_type=action_type,
            created_at=created_at or datetime.utcnow(),
            metadata_json=dict(metadata_json or {}),
        )
        return await self._repository.save_feedback(event)

    async def get_feedback_for_recommendation(
        self,
        recommendation_id: str,
        limit: int = 100,
    ) -> Sequence[RecommendationFeedback]:
        return await self._repository.get_feedback_by_recommendation(
            recommendation_id=recommendation_id,
            limit=limit,
        )

    async def get_feedback_for_user(
        self,
        user_id: str,
        limit: int = 100,
    ) -> Sequence[RecommendationFeedback]:
        return await self._repository.get_feedback_by_user(user_id=user_id, limit=limit)

