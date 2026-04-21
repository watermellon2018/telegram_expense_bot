"""
Service layer for user recommendation settings.
"""

from typing import Optional

from recommendation.models import (
    RecommendationSettings,
    UserRecommendationSettings,
    UserRecommendationSettingsUpdate,
)
from recommendation.repositories.interfaces import SettingsRepository


class RecommendationSettingsService:
    """Facade over settings repository for create/read/update workflows."""

    def __init__(self, repository: SettingsRepository):
        self._repository = repository

    async def get_user_settings(self, user_id: str) -> UserRecommendationSettings:
        return await self._repository.get_user_settings(user_id)

    async def get_runtime_settings(
        self,
        user_id: str,
        project_id: Optional[int] = None,
    ) -> RecommendationSettings:
        return await self._repository.get_settings(user_id, project_id)

    async def update_user_settings(
        self,
        user_id: str,
        update: UserRecommendationSettingsUpdate,
    ) -> UserRecommendationSettings:
        return await self._repository.upsert_user_settings(user_id, update)

