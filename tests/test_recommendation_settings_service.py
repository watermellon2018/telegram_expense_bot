import pytest

from recommendation.models import UserRecommendationSettingsUpdate
from recommendation.repositories.in_memory import InMemorySettingsRepository
from recommendation.settings_service import RecommendationSettingsService
from recommendation.types import RecommendationType


@pytest.mark.asyncio
async def test_missing_user_settings_return_defaults():
    repository = InMemorySettingsRepository()
    service = RecommendationSettingsService(repository)

    settings = await service.get_user_settings("u-1")

    assert settings.id is None
    assert settings.user_id == "u-1"
    assert settings.recommendations_enabled is True
    assert settings.max_recommendations_per_request == 3
    assert settings.show_positive_recommendations is True
    assert settings.hidden_recommendation_types == tuple()
    assert settings.monthly_budget_total is None


@pytest.mark.asyncio
async def test_user_settings_can_be_created_and_updated():
    repository = InMemorySettingsRepository()
    service = RecommendationSettingsService(repository)

    created = await service.update_user_settings(
        user_id="u-2",
        update=UserRecommendationSettingsUpdate(
            recommendations_enabled=False,
            max_recommendations_per_request=5,
            show_positive_recommendations=False,
            hidden_recommendation_types=(
                RecommendationType.CASHBACK_OPPORTUNITY,
                RecommendationType.HIGH_RECURRING_SHARE,
            ),
            monthly_budget_total=12000.50,
        ),
    )

    assert created.id is not None
    assert created.recommendations_enabled is False
    assert created.max_recommendations_per_request == 5
    assert created.show_positive_recommendations is False
    assert created.hidden_recommendation_types == (
        RecommendationType.CASHBACK_OPPORTUNITY,
        RecommendationType.HIGH_RECURRING_SHARE,
    )
    assert created.monthly_budget_total == 12000.50

    updated = await service.update_user_settings(
        user_id="u-2",
        update=UserRecommendationSettingsUpdate(
            recommendations_enabled=True,
            max_recommendations_per_request=2,
            clear_monthly_budget_total=True,
        ),
    )

    assert updated.id == created.id
    assert updated.recommendations_enabled is True
    assert updated.max_recommendations_per_request == 2
    assert updated.monthly_budget_total is None

    read_back = await service.get_user_settings("u-2")
    assert read_back.id == created.id
    assert read_back.recommendations_enabled is True
    assert read_back.max_recommendations_per_request == 2


@pytest.mark.asyncio
async def test_runtime_settings_are_mapped_from_user_settings():
    repository = InMemorySettingsRepository()
    service = RecommendationSettingsService(repository)

    await service.update_user_settings(
        user_id="u-3",
        update=UserRecommendationSettingsUpdate(
            recommendations_enabled=False,
            max_recommendations_per_request=7,
            hidden_recommendation_types=(RecommendationType.FORECAST_OVERSPEND,),
            monthly_budget_total=9000.0,
        ),
    )

    runtime = await service.get_runtime_settings(user_id="u-3", project_id=None)

    assert runtime.enabled is False
    assert runtime.max_recommendations == 7
    assert runtime.hidden_recommendation_types == (RecommendationType.FORECAST_OVERSPEND,)
    assert runtime.monthly_budget_total == 9000.0

