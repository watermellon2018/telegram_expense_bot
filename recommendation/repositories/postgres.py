"""
PostgreSQL-backed repositories for recommendation settings, history and feedback.
"""

from datetime import datetime
from typing import List, Optional, Sequence

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
from utils import db


class PostgresSettingsRepository(SettingsRepository):
    """Persist user recommendation settings in PostgreSQL."""

    async def get_settings(self, user_id: str, project_id: Optional[int]) -> RecommendationSettings:
        user_settings = await self.get_user_settings(user_id)
        return user_settings.to_runtime_settings()

    async def get_user_settings(self, user_id: str) -> UserRecommendationSettings:
        row = await db.fetchrow(
            """
            SELECT
                id,
                user_id,
                recommendations_enabled,
                max_recommendations_per_request,
                show_positive_recommendations,
                hidden_recommendation_types,
                monthly_budget_total,
                created_at,
                updated_at
            FROM user_recommendation_settings
            WHERE user_id = $1
            """,
            user_id,
        )
        if row is None:
            return build_default_user_recommendation_settings(user_id)

        return self._row_to_user_settings(row)

    async def upsert_user_settings(
        self,
        user_id: str,
        update: UserRecommendationSettingsUpdate,
    ) -> UserRecommendationSettings:
        current = await self.get_user_settings(user_id)
        merged = current.apply_update(update)

        hidden_types: List[str] = [item.value for item in merged.hidden_recommendation_types]

        row = await db.fetchrow(
            """
            INSERT INTO user_recommendation_settings (
                user_id,
                recommendations_enabled,
                max_recommendations_per_request,
                show_positive_recommendations,
                hidden_recommendation_types,
                monthly_budget_total
            )
            VALUES ($1, $2, $3, $4, $5::text[], $6)
            ON CONFLICT (user_id) DO UPDATE SET
                recommendations_enabled = EXCLUDED.recommendations_enabled,
                max_recommendations_per_request = EXCLUDED.max_recommendations_per_request,
                show_positive_recommendations = EXCLUDED.show_positive_recommendations,
                hidden_recommendation_types = EXCLUDED.hidden_recommendation_types,
                monthly_budget_total = EXCLUDED.monthly_budget_total,
                updated_at = NOW()
            RETURNING
                id,
                user_id,
                recommendations_enabled,
                max_recommendations_per_request,
                show_positive_recommendations,
                hidden_recommendation_types,
                monthly_budget_total,
                created_at,
                updated_at
            """,
            user_id,
            merged.recommendations_enabled,
            merged.max_recommendations_per_request,
            merged.show_positive_recommendations,
            hidden_types,
            merged.monthly_budget_total,
        )

        if row is None:
            return merged

        return self._row_to_user_settings(row)

    @staticmethod
    def _row_to_user_settings(row) -> UserRecommendationSettings:
        hidden_types = tuple(row["hidden_recommendation_types"] or [])
        return UserRecommendationSettings(
            id=int(row["id"]),
            user_id=str(row["user_id"]),
            recommendations_enabled=bool(row["recommendations_enabled"]),
            max_recommendations_per_request=int(row["max_recommendations_per_request"]),
            show_positive_recommendations=bool(row["show_positive_recommendations"]),
            hidden_recommendation_types=hidden_types,
            monthly_budget_total=(
                float(row["monthly_budget_total"])
                if row["monthly_budget_total"] is not None
                else None
            ),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


class PostgresHistoryRepository(HistoryRepository):
    """Persist recommendation history in PostgreSQL."""

    async def insert_generated(
        self,
        entries: Sequence[RecommendationHistoryEntry],
    ) -> Sequence[RecommendationHistoryEntry]:
        persisted: List[RecommendationHistoryEntry] = []
        for entry in entries:
            row = await db.fetchrow(
                """
                INSERT INTO recommendation_history (
                    user_id,
                    recommendation_type,
                    period_key,
                    entity_type,
                    entity_id,
                    payload_json,
                    score,
                    status,
                    generated_at,
                    shown_at
                )
                VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7, $8, $9, $10)
                RETURNING
                    id,
                    user_id,
                    recommendation_type,
                    period_key,
                    entity_type,
                    entity_id,
                    payload_json,
                    score,
                    status,
                    generated_at,
                    shown_at
                """,
                entry.user_id,
                entry.recommendation_type.value,
                entry.period_key,
                entry.entity_type,
                entry.entity_id,
                dict(entry.payload_json),
                entry.score,
                entry.status.value,
                entry.generated_at,
                entry.shown_at,
            )
            if row is None:
                continue
            persisted.append(self._row_to_history_entry(row))
        return persisted

    async def mark_as_shown(
        self,
        history_ids: Sequence[int],
    ) -> int:
        if not history_ids:
            return 0

        shown_at = datetime.utcnow()
        result = await db.execute(
            """
            UPDATE recommendation_history
            SET
                status = $2,
                shown_at = COALESCE(shown_at, $3)
            WHERE id = ANY($1::int[])
            """,
            list(history_ids),
            RecommendationHistoryStatus.SHOWN.value,
            shown_at,
        )
        return int(result.split()[-1])

    async def get_recent_history(
        self,
        user_id: str,
        period_key: Optional[str] = None,
        limit: int = 50,
    ) -> Sequence[RecommendationHistoryEntry]:
        if period_key is None:
            rows = await db.fetch(
                """
                SELECT
                    id,
                    user_id,
                    recommendation_type,
                    period_key,
                    entity_type,
                    entity_id,
                    payload_json,
                    score,
                    status,
                    generated_at,
                    shown_at
                FROM recommendation_history
                WHERE user_id = $1
                ORDER BY generated_at DESC, id DESC
                LIMIT $2
                """,
                user_id,
                limit,
            )
        else:
            rows = await db.fetch(
                """
                SELECT
                    id,
                    user_id,
                    recommendation_type,
                    period_key,
                    entity_type,
                    entity_id,
                    payload_json,
                    score,
                    status,
                    generated_at,
                    shown_at
                FROM recommendation_history
                WHERE user_id = $1 AND period_key = $2
                ORDER BY generated_at DESC, id DESC
                LIMIT $3
                """,
                user_id,
                period_key,
                limit,
            )
        return [self._row_to_history_entry(row) for row in rows]

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

    @staticmethod
    def _row_to_history_entry(row) -> RecommendationHistoryEntry:
        payload = row["payload_json"] or {}
        if not isinstance(payload, dict):
            payload = dict(payload)

        return RecommendationHistoryEntry(
            id=int(row["id"]),
            user_id=str(row["user_id"]),
            recommendation_type=row["recommendation_type"],
            period_key=str(row["period_key"]),
            entity_type=row["entity_type"],
            entity_id=(str(row["entity_id"]) if row["entity_id"] is not None else None),
            payload_json=payload,
            score=float(row["score"]),
            status=row["status"],
            generated_at=row["generated_at"],
            shown_at=row["shown_at"],
        )


class PostgresFeedbackRepository(FeedbackRepository):
    """Persist recommendation feedback events in PostgreSQL."""

    async def save_feedback(self, feedback: RecommendationFeedback) -> RecommendationFeedback:
        row = await db.fetchrow(
            """
            INSERT INTO recommendation_feedback_events (
                recommendation_id,
                user_id,
                action_type,
                metadata_json,
                created_at
            )
            VALUES ($1, $2, $3, $4::jsonb, $5)
            RETURNING
                id,
                recommendation_id,
                user_id,
                action_type,
                metadata_json,
                created_at
            """,
            feedback.recommendation_id,
            feedback.user_id,
            feedback.action_type.value,
            dict(feedback.metadata_json),
            feedback.created_at,
        )
        if row is None:
            return feedback
        return self._row_to_feedback(row)

    async def get_feedback(
        self,
        user_id: str,
        project_id: Optional[int],
        limit: int = 50,
    ) -> Sequence[RecommendationFeedback]:
        return await self.get_feedback_by_user(user_id=user_id, limit=limit)

    async def get_feedback_by_recommendation(
        self,
        recommendation_id: str,
        limit: int = 100,
    ) -> Sequence[RecommendationFeedback]:
        rows = await db.fetch(
            """
            SELECT
                id,
                recommendation_id,
                user_id,
                action_type,
                metadata_json,
                created_at
            FROM recommendation_feedback_events
            WHERE recommendation_id = $1
            ORDER BY created_at DESC, id DESC
            LIMIT $2
            """,
            recommendation_id,
            limit,
        )
        return [self._row_to_feedback(row) for row in rows]

    async def get_feedback_by_user(
        self,
        user_id: str,
        limit: int = 100,
    ) -> Sequence[RecommendationFeedback]:
        rows = await db.fetch(
            """
            SELECT
                id,
                recommendation_id,
                user_id,
                action_type,
                metadata_json,
                created_at
            FROM recommendation_feedback_events
            WHERE user_id = $1
            ORDER BY created_at DESC, id DESC
            LIMIT $2
            """,
            user_id,
            limit,
        )
        return [self._row_to_feedback(row) for row in rows]

    @staticmethod
    def _row_to_feedback(row) -> RecommendationFeedback:
        metadata = row["metadata_json"] or {}
        if not isinstance(metadata, dict):
            metadata = dict(metadata)

        return RecommendationFeedback(
            id=int(row["id"]),
            recommendation_id=str(row["recommendation_id"]),
            user_id=str(row["user_id"]),
            action_type=row["action_type"],
            created_at=row["created_at"],
            metadata_json=metadata,
        )
