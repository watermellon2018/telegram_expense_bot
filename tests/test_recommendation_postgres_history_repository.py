from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest

from recommendation.models import RecommendationHistoryEntry
from recommendation.repositories.postgres import PostgresHistoryRepository
from recommendation.types import RecommendationHistoryStatus, RecommendationType


@pytest.mark.asyncio
async def test_postgres_history_insert_generated_and_mark_shown():
    repository = PostgresHistoryRepository()
    now = datetime.utcnow()

    returned_row = {
        "id": 11,
        "user_id": "pg-h-1",
        "recommendation_type": "forecast_overspend",
        "period_key": "2026-04",
        "entity_type": "month",
        "entity_id": "2026-04",
        "payload_json": {"source_rule_id": "r1"},
        "score": 0.8,
        "status": "generated",
        "generated_at": now,
        "shown_at": None,
    }

    with patch(
        "recommendation.repositories.postgres.db.fetchrow",
        new=AsyncMock(return_value=returned_row),
    ):
        inserted = await repository.insert_generated(
            [
                RecommendationHistoryEntry(
                    id=None,
                    user_id="pg-h-1",
                    recommendation_type=RecommendationType.FORECAST_OVERSPEND,
                    period_key="2026-04",
                    entity_type="month",
                    entity_id="2026-04",
                    payload_json={"source_rule_id": "r1"},
                    score=0.8,
                )
            ]
        )

    assert len(inserted) == 1
    assert inserted[0].id == 11
    assert inserted[0].status == RecommendationHistoryStatus.GENERATED

    with patch(
        "recommendation.repositories.postgres.db.execute",
        new=AsyncMock(return_value="UPDATE 1"),
    ):
        updated = await repository.mark_as_shown([11])
    assert updated == 1


@pytest.mark.asyncio
async def test_postgres_history_query_by_user_and_period():
    repository = PostgresHistoryRepository()
    now = datetime.utcnow()
    rows = [
        {
            "id": 21,
            "user_id": "pg-h-2",
            "recommendation_type": "cashback_opportunity",
            "period_key": "2026-04",
            "entity_type": "category",
            "entity_id": "food",
            "payload_json": {"source_rule_id": "r2", "project_id": None},
            "score": 0.5,
            "status": "shown",
            "generated_at": now,
            "shown_at": now,
        }
    ]

    with patch(
        "recommendation.repositories.postgres.db.fetch",
        new=AsyncMock(return_value=rows),
    ):
        history = await repository.get_recent_history("pg-h-2", period_key="2026-04")

    assert len(history) == 1
    assert history[0].recommendation_type == RecommendationType.CASHBACK_OPPORTUNITY
    assert history[0].period_key == "2026-04"

