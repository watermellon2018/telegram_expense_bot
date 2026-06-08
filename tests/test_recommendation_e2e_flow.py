from datetime import datetime

import pytest

from recommendation.analytics import PreparedAnalyticsService
from recommendation.formatter import DefaultRecommendationFormatter
from recommendation.models import RecommendationRequest, RecommendationSettings
from recommendation.outliers import BaselineOutlierHandler
from recommendation.pipeline import RecommendationPipeline
from recommendation.ranking import ScoreRankingService
from recommendation.repositories.in_memory import (
    InMemoryFeedbackRepository,
    InMemoryHistoryRepository,
    InMemorySettingsRepository,
)
from recommendation.rule_engine import DefaultRuleEngine
from recommendation.rules import build_mvp_rules


@pytest.mark.asyncio
async def test_recommendation_pipeline_end_to_end_flow_with_history():
    settings_repo = InMemorySettingsRepository()
    history_repo = InMemoryHistoryRepository()
    feedback_repo = InMemoryFeedbackRepository()
    await settings_repo.set_settings(
        user_id="u-e2e",
        project_id=None,
        settings=RecommendationSettings(enabled=True, max_recommendations=3),
    )

    pipeline = RecommendationPipeline(
        analytics_service=PreparedAnalyticsService(),
        outlier_handler=BaselineOutlierHandler(),
        rule_engine=DefaultRuleEngine(build_mvp_rules()),
        ranking_service=ScoreRankingService(),
        formatter=DefaultRecommendationFormatter(),
        settings_repository=settings_repo,
        history_repository=history_repo,
        feedback_repository=feedback_repo,
    )

    request = RecommendationRequest(
        user_id="u-e2e",
        requested_at=datetime(2026, 4, 21, 12, 0, 0),
        metrics={
            "total_expense_prev_month": 1300.0,
            "total_expense_3m_baseline": 1400.0,
            "same_day_prev_month_expense": 980.0,
            "prev_month_net_balance": -150.0,
            "prev_month_recurring_share": 0.42,
            "monthly_budget_total": 1900.0,
        },
        dimensions={
            "category_share_prev_month": {"food": 0.25, "transport": 0.18, "home": 0.12},
            "category_share_3m_baseline": {"food": 0.24, "transport": 0.19, "home": 0.11},
        },
        events=(
            {"date": "2026-04-01", "amount": 160.0, "type": "expense", "category": "food"},
            {"date": "2026-04-01", "amount": 140.0, "type": "expense", "category": "food"},
            {"date": "2026-04-01", "amount": 120.0, "type": "expense", "category": "food"},
            {"date": "2026-04-02", "amount": 900.0, "type": "income", "category": "salary"},
            {"date": "2026-04-03", "amount": 520.0, "type": "expense", "category": "transport"},
            {"date": "2026-04-04", "amount": 420.0, "type": "expense", "category": "home", "is_recurring": True},
            {"date": "2026-04-05", "amount": 430.0, "type": "expense", "category": "home", "is_recurring": True},
            {"date": "2026-04-06", "amount": 610.0, "type": "expense", "category": "food"},
            {"date": "2026-04-07", "amount": 310.0, "type": "expense", "category": "transport"},
            {"date": "2026-04-12", "amount": 350.0, "type": "expense", "category": "entertainment"},
        ),
    )

    first_run = await pipeline.generate(request)
    assert first_run
    assert len(first_run) <= 3
    assert all(item.message for item in first_run)

    history = await history_repo.get_recent(user_id="u-e2e", project_id=None, limit=10)
    assert len(history) == len(first_run)

    second_run = await pipeline.generate(request)
    assert second_run
    assert len(second_run) <= 3
    assert second_run[0].score <= first_run[0].score
