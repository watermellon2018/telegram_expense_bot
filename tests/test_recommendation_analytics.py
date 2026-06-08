from datetime import datetime

import pytest

from recommendation.analytics import PreparedAnalyticsService
from recommendation.models import RecommendationRequest


@pytest.mark.asyncio
async def test_prepared_analytics_service_builds_current_and_dynamic_signals():
    service = PreparedAnalyticsService()
    request_time = datetime(2026, 4, 20, 12, 0, 0)
    request = RecommendationRequest(
        user_id="u-analytics-1",
        requested_at=request_time,
        metrics={
            "total_expense_prev_month": 900.0,
            "total_expense_3m_baseline": 850.0,
            "same_day_prev_month_expense": 700.0,
            "prev_month_net_balance": 200.0,
            "prev_month_recurring_share": 0.35,
        },
        events=(
            {"date": "2026-04-01", "amount": 120.0, "type": "expense", "category_id": 1},
            {"date": "2026-04-02", "amount": 80.0, "type": "expense", "category_id": 1},
            {"date": "2026-04-03", "amount": 400.0, "type": "expense", "category_id": 2},
            {"date": "2026-04-04", "amount": 1000.0, "type": "income"},
            {"date": "2026-04-05", "amount": 300.0, "type": "expense", "category_id": 2},
        ),
    )

    snapshot = await service.build_snapshot(request)

    assert snapshot.metrics["total_expense"] == 900.0
    assert snapshot.metrics["total_income"] == 1000.0
    assert snapshot.metrics["net_balance"] == 100.0
    assert snapshot.metrics["delta_vs_prev_month"] == 0.0
    assert snapshot.metrics["delta_vs_3m_baseline"] == 50.0
    assert snapshot.metrics["delta_vs_same_day_prev_month"] == 200.0
    assert snapshot.metrics["spend_forecast"] > 0.0
    assert "category_share_current" in snapshot.dimensions


@pytest.mark.asyncio
async def test_prepared_analytics_service_builds_behavioral_and_positive_signals():
    service = PreparedAnalyticsService()
    request_time = datetime(2026, 4, 15, 12, 0, 0)
    request = RecommendationRequest(
        user_id="u-analytics-2",
        requested_at=request_time,
        dimensions={
            "category_share_prev_month": {
                "food": 0.50,
                "transport": 0.20,
            }
        },
        metrics={
            "total_expense_prev_month": 1200.0,
            "prev_month_net_balance": -200.0,
            "prev_month_recurring_share": 0.40,
        },
        metadata={"small_expense_threshold": 150.0},
        events=(
            {"date": "2026-04-01", "amount": 100.0, "type": "expense", "category": "food"},
            {"date": "2026-04-01", "amount": 90.0, "type": "expense", "category": "food"},
            {"date": "2026-04-01", "amount": 80.0, "type": "expense", "category": "food"},
            {"date": "2026-04-02", "amount": 500.0, "type": "income"},
            {"date": "2026-04-03", "amount": 320.0, "type": "expense", "category": "transport"},
            {"date": "2026-04-06", "amount": 60.0, "type": "expense", "category": "transport", "is_recurring": True},
        ),
    )

    snapshot = await service.build_snapshot(request)

    assert snapshot.metrics["weekday_spend_total"] >= 0.0
    assert snapshot.metrics["post_income_spike_count"] >= 1.0
    assert snapshot.metrics["repeated_small_tx_count"] >= 3.0
    assert snapshot.metrics["positive_improved_balance"] == 1.0
    assert snapshot.metrics["positive_reduced_recurring_share"] == 1.0

    second_snapshot = await service.build_snapshot(request)
    assert snapshot.metrics == second_snapshot.metrics

