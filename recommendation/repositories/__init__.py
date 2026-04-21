"""Repositories for recommendation module."""

from recommendation.repositories.in_memory import (
    InMemoryFeedbackRepository,
    InMemoryHistoryRepository,
    InMemorySettingsRepository,
)
from recommendation.repositories.interfaces import FeedbackRepository, HistoryRepository, SettingsRepository
from recommendation.repositories.postgres import (
    PostgresFeedbackRepository,
    PostgresHistoryRepository,
    PostgresSettingsRepository,
)

__all__ = [
    "FeedbackRepository",
    "HistoryRepository",
    "SettingsRepository",
    "InMemoryFeedbackRepository",
    "InMemoryHistoryRepository",
    "InMemorySettingsRepository",
    "PostgresFeedbackRepository",
    "PostgresHistoryRepository",
    "PostgresSettingsRepository",
]
