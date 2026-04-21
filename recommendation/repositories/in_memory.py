"""
In-memory repository implementations for recommendation module skeleton.
"""

from datetime import datetime
from typing import Dict, List, Optional, Sequence

from recommendation.models import (
    RecommendationFeedback,
    RecommendationHistoryEntry,
    RecommendationRecord,
    RecommendationSettings,
    UserRecommendationSettings,
    UserRecommendationSettingsUpdate,
    build_default_user_recommendation_settings,
)
from recommendation.repositories.interfaces import FeedbackRepository, HistoryRepository, SettingsRepository
from recommendation.types import RecommendationHistoryStatus


class InMemorySettingsRepository(SettingsRepository):
    """In-memory settings repository keyed by user_id."""

    def __init__(self, default_settings: Optional[RecommendationSettings] = None):
        runtime_defaults = default_settings or RecommendationSettings()
        self._settings: Dict[str, UserRecommendationSettings] = {}
        self._runtime_defaults = runtime_defaults
        self._runtime_settings: Dict[str, RecommendationSettings] = {}

    async def get_settings(self, user_id: str, project_id: Optional[int]) -> RecommendationSettings:
        runtime_override = self._runtime_settings.get(user_id)
        if runtime_override is not None:
            return runtime_override

        user_settings = await self.get_user_settings(user_id)
        runtime = user_settings.to_runtime_settings()
        return RecommendationSettings(
            enabled=runtime.enabled,
            max_recommendations=runtime.max_recommendations,
            min_score=self._runtime_defaults.min_score,
            rule_overrides=self._runtime_defaults.rule_overrides,
            show_positive_recommendations=runtime.show_positive_recommendations,
            hidden_recommendation_types=runtime.hidden_recommendation_types,
            monthly_budget_total=runtime.monthly_budget_total,
        )

    async def get_user_settings(self, user_id: str) -> UserRecommendationSettings:
        stored = self._settings.get(user_id)
        if stored is not None:
            return stored

        return build_default_user_recommendation_settings(user_id)

    async def upsert_user_settings(
        self,
        user_id: str,
        update: UserRecommendationSettingsUpdate,
    ) -> UserRecommendationSettings:
        current = await self.get_user_settings(user_id)
        merged = current.apply_update(update)
        if merged.id is None:
            merged = UserRecommendationSettings(
                id=len(self._settings) + 1,
                user_id=merged.user_id,
                recommendations_enabled=merged.recommendations_enabled,
                max_recommendations_per_request=merged.max_recommendations_per_request,
                show_positive_recommendations=merged.show_positive_recommendations,
                hidden_recommendation_types=merged.hidden_recommendation_types,
                monthly_budget_total=merged.monthly_budget_total,
                created_at=merged.created_at,
                updated_at=merged.updated_at,
            )
        self._settings[user_id] = merged
        self._runtime_settings[user_id] = RecommendationSettings(
            enabled=merged.recommendations_enabled,
            max_recommendations=merged.max_recommendations_per_request,
            min_score=self._runtime_defaults.min_score,
            rule_overrides=self._runtime_defaults.rule_overrides,
            show_positive_recommendations=merged.show_positive_recommendations,
            hidden_recommendation_types=merged.hidden_recommendation_types,
            monthly_budget_total=merged.monthly_budget_total,
        )
        return merged

    async def set_settings(
        self,
        user_id: str,
        project_id: Optional[int],
        settings: RecommendationSettings,
    ) -> None:
        """Compatibility helper used in tests."""
        current = await self.get_user_settings(user_id)
        merged = UserRecommendationSettings(
            id=current.id,
            user_id=user_id,
            recommendations_enabled=settings.enabled,
            max_recommendations_per_request=settings.max_recommendations,
            show_positive_recommendations=settings.show_positive_recommendations,
            hidden_recommendation_types=settings.hidden_recommendation_types,
            monthly_budget_total=settings.monthly_budget_total,
            created_at=current.created_at,
            updated_at=current.updated_at,
        )
        self._settings[user_id] = merged
        self._runtime_settings[user_id] = settings


class InMemoryHistoryRepository(HistoryRepository):
    """In-memory recommendations history."""

    def __init__(self):
        self._entries: List[RecommendationHistoryEntry] = []
        self._next_id = 1

    async def insert_generated(
        self,
        entries: Sequence[RecommendationHistoryEntry],
    ) -> Sequence[RecommendationHistoryEntry]:
        persisted: List[RecommendationHistoryEntry] = []
        for entry in entries:
            generated_at = entry.generated_at or datetime.utcnow()
            saved = RecommendationHistoryEntry(
                id=self._next_id,
                user_id=entry.user_id,
                recommendation_type=entry.recommendation_type,
                period_key=entry.period_key,
                entity_type=entry.entity_type,
                entity_id=entry.entity_id,
                payload_json=dict(entry.payload_json),
                score=entry.score,
                status=entry.status,
                generated_at=generated_at,
                shown_at=entry.shown_at,
            )
            self._next_id += 1
            self._entries.append(saved)
            persisted.append(saved)
        return persisted

    async def mark_as_shown(
        self,
        history_ids: Sequence[int],
    ) -> int:
        if not history_ids:
            return 0

        ids = set(history_ids)
        now = datetime.utcnow()
        updated = 0
        next_entries: List[RecommendationHistoryEntry] = []
        for entry in self._entries:
            if entry.id not in ids:
                next_entries.append(entry)
                continue
            if entry.status == RecommendationHistoryStatus.SHOWN:
                next_entries.append(entry)
                continue

            updated += 1
            next_entries.append(
                RecommendationHistoryEntry(
                    id=entry.id,
                    user_id=entry.user_id,
                    recommendation_type=entry.recommendation_type,
                    period_key=entry.period_key,
                    entity_type=entry.entity_type,
                    entity_id=entry.entity_id,
                    payload_json=entry.payload_json,
                    score=entry.score,
                    status=RecommendationHistoryStatus.SHOWN,
                    generated_at=entry.generated_at,
                    shown_at=now,
                )
            )
        self._entries = next_entries
        return updated

    async def get_recent_history(
        self,
        user_id: str,
        period_key: Optional[str] = None,
        limit: int = 50,
    ) -> Sequence[RecommendationHistoryEntry]:
        filtered = [
            entry
            for entry in self._entries
            if entry.user_id == user_id and (period_key is None or entry.period_key == period_key)
        ]
        filtered.sort(key=lambda item: item.generated_at, reverse=True)
        return filtered[:limit]

    async def save_presented(self, records: Sequence[RecommendationRecord]) -> None:
        entries = [
            RecommendationHistoryEntry(
                id=None,
                user_id=record.user_id,
                recommendation_type=record.recommendation_type,
                period_key=str(record.payload.get("period_key") or "unspecified"),
                entity_type=record.payload.get("entity_type"),
                entity_id=(
                    str(record.payload.get("entity_id"))
                    if record.payload.get("entity_id") is not None
                    else None
                ),
                payload_json={
                    "recommendation_id": record.recommendation_id,
                    "source_rule_id": record.source_rule_id,
                    "project_id": record.project_id,
                    **dict(record.payload),
                },
                score=record.score,
                status=RecommendationHistoryStatus.SHOWN,
                generated_at=record.presented_at,
                shown_at=record.presented_at,
            )
            for record in records
        ]
        await self.insert_generated(entries)

    async def get_recent(
        self,
        user_id: str,
        project_id: Optional[int],
        limit: int = 50,
    ) -> Sequence[RecommendationRecord]:
        entries = await self.get_recent_history(user_id=user_id, period_key=None, limit=limit * 5)
        records: List[RecommendationRecord] = []
        for entry in entries:
            if entry.status != RecommendationHistoryStatus.SHOWN:
                continue
            payload = dict(entry.payload_json)
            payload_project_id = payload.get("project_id")
            if payload_project_id is not None:
                try:
                    payload_project_id = int(payload_project_id)
                except (TypeError, ValueError):
                    payload_project_id = None

            if payload_project_id != project_id:
                continue

            records.append(
                RecommendationRecord(
                    recommendation_id=str(payload.get("recommendation_id") or f"history-{entry.id}"),
                    user_id=entry.user_id,
                    project_id=project_id,
                    source_rule_id=str(payload.get("source_rule_id") or "unknown_rule"),
                    recommendation_type=entry.recommendation_type,
                    score=entry.score,
                    presented_at=entry.shown_at or entry.generated_at,
                    payload=payload,
                )
            )
            if len(records) >= limit:
                break
        return records


class InMemoryFeedbackRepository(FeedbackRepository):
    """In-memory recommendation feedback storage."""

    def __init__(self):
        self._feedback: List[RecommendationFeedback] = []
        self._next_id = 1

    async def save_feedback(self, feedback: RecommendationFeedback) -> RecommendationFeedback:
        saved = RecommendationFeedback(
            id=feedback.id if feedback.id is not None else self._next_id,
            recommendation_id=feedback.recommendation_id,
            user_id=feedback.user_id,
            action_type=feedback.action_type,
            created_at=feedback.created_at,
            metadata_json=dict(feedback.metadata_json),
        )
        if feedback.id is None:
            self._next_id += 1
        self._feedback.append(saved)
        return saved

    async def get_feedback(
        self,
        user_id: str,
        project_id: Optional[int],
        limit: int = 50,
    ) -> Sequence[RecommendationFeedback]:
        filtered = [item for item in self._feedback if item.user_id == user_id]
        filtered.sort(
            key=lambda item: (item.created_at, item.id if item.id is not None else 0),
            reverse=True,
        )
        return filtered[:limit]

    async def get_feedback_by_recommendation(
        self,
        recommendation_id: str,
        limit: int = 100,
    ) -> Sequence[RecommendationFeedback]:
        filtered = [
            item
            for item in self._feedback
            if item.recommendation_id == recommendation_id
        ]
        filtered.sort(
            key=lambda item: (item.created_at, item.id if item.id is not None else 0),
            reverse=True,
        )
        return filtered[:limit]

    async def get_feedback_by_user(
        self,
        user_id: str,
        limit: int = 100,
    ) -> Sequence[RecommendationFeedback]:
        filtered = [item for item in self._feedback if item.user_id == user_id]
        filtered.sort(
            key=lambda item: (item.created_at, item.id if item.id is not None else 0),
            reverse=True,
        )
        return filtered[:limit]
