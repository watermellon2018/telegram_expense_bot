from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest

from recommendation.models import UserRecommendationSettingsUpdate
from recommendation.repositories.postgres import PostgresSettingsRepository
from recommendation.types import RecommendationType


@pytest.mark.asyncio
async def test_postgres_repository_returns_defaults_if_row_missing():
    repository = PostgresSettingsRepository()

    with patch(
        "recommendation.repositories.postgres.db.fetchrow",
        new=AsyncMock(return_value=None),
    ):
        settings = await repository.get_user_settings("pg-user-1")

    assert settings.id is None
    assert settings.user_id == "pg-user-1"
    assert settings.recommendations_enabled is True
    assert settings.max_recommendations_per_request == 3


@pytest.mark.asyncio
async def test_postgres_repository_upsert_create_update_flow():
    repository = PostgresSettingsRepository()
    now = datetime.utcnow()
    db_row = {
        "id": 10,
        "user_id": "pg-user-2",
        "recommendations_enabled": False,
        "max_recommendations_per_request": 6,
        "show_positive_recommendations": False,
        "hidden_recommendation_types": [
            "forecast_overspend",
            "cashback_opportunity",
        ],
        "monthly_budget_total": 15500.0,
        "created_at": now,
        "updated_at": now,
    }

    with patch(
        "recommendation.repositories.postgres.db.fetchrow",
        new=AsyncMock(side_effect=[None, db_row]),
    ):
        settings = await repository.upsert_user_settings(
            "pg-user-2",
            UserRecommendationSettingsUpdate(
                recommendations_enabled=False,
                max_recommendations_per_request=6,
                show_positive_recommendations=False,
                hidden_recommendation_types=(
                    RecommendationType.FORECAST_OVERSPEND,
                    RecommendationType.CASHBACK_OPPORTUNITY,
                ),
                monthly_budget_total=15500.0,
            ),
        )

    assert settings.id == 10
    assert settings.user_id == "pg-user-2"
    assert settings.recommendations_enabled is False
    assert settings.max_recommendations_per_request == 6
    assert settings.hidden_recommendation_types == (
        RecommendationType.FORECAST_OVERSPEND,
        RecommendationType.CASHBACK_OPPORTUNITY,
    )
    assert settings.monthly_budget_total == 15500.0

