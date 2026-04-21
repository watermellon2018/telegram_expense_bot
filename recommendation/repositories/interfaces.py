"""
Repository interfaces for recommendation settings/history/feedback.
"""

from abc import ABC, abstractmethod
from typing import Optional, Sequence

from recommendation.models import (
    RecommendationFeedback,
    RecommendationHistoryEntry,
    RecommendationRecord,
    RecommendationSettings,
    UserRecommendationSettings,
    UserRecommendationSettingsUpdate,
)


class SettingsRepository(ABC):
    """Persistent settings for recommendation module."""

    @abstractmethod
    async def get_settings(self, user_id: str, project_id: Optional[int]) -> RecommendationSettings:
        """Return settings for current user/project scope."""

    @abstractmethod
    async def get_user_settings(self, user_id: str) -> UserRecommendationSettings:
        """Return persisted user settings or defaults."""

    @abstractmethod
    async def upsert_user_settings(
        self,
        user_id: str,
        update: UserRecommendationSettingsUpdate,
    ) -> UserRecommendationSettings:
        """Create or update user settings and return stored version."""


class HistoryRepository(ABC):
    """Storage for already shown recommendations."""

    @abstractmethod
    async def insert_generated(
        self,
        entries: Sequence[RecommendationHistoryEntry],
    ) -> Sequence[RecommendationHistoryEntry]:
        """Persist generated recommendation history rows."""

    @abstractmethod
    async def mark_as_shown(
        self,
        history_ids: Sequence[int],
    ) -> int:
        """Mark generated recommendations as shown and return updated count."""

    @abstractmethod
    async def get_recent_history(
        self,
        user_id: str,
        period_key: Optional[str] = None,
        limit: int = 50,
    ) -> Sequence[RecommendationHistoryEntry]:
        """Return recent history for user, optionally filtered by period."""

    @abstractmethod
    async def save_presented(self, records: Sequence[RecommendationRecord]) -> None:
        """Persist presented recommendations."""

    @abstractmethod
    async def get_recent(
        self,
        user_id: str,
        project_id: Optional[int],
        limit: int = 50,
    ) -> Sequence[RecommendationRecord]:
        """Return recent recommendations history."""


class FeedbackRepository(ABC):
    """Storage for user feedback on recommendations."""

    @abstractmethod
    async def save_feedback(self, feedback: RecommendationFeedback) -> RecommendationFeedback:
        """Persist feedback event and return stored entry."""

    @abstractmethod
    async def get_feedback(
        self,
        user_id: str,
        project_id: Optional[int],
        limit: int = 50,
    ) -> Sequence[RecommendationFeedback]:
        """Compatibility method; returns recent feedback entries by user."""

    @abstractmethod
    async def get_feedback_by_recommendation(
        self,
        recommendation_id: str,
        limit: int = 100,
    ) -> Sequence[RecommendationFeedback]:
        """Return feedback history for recommendation."""

    @abstractmethod
    async def get_feedback_by_user(
        self,
        user_id: str,
        limit: int = 100,
    ) -> Sequence[RecommendationFeedback]:
        """Return feedback history for user."""
