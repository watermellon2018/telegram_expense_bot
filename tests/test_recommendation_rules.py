from datetime import datetime

import pytest

from recommendation.models import AnalyticsSnapshot, RecommendationSettings
from recommendation.rule_engine import DefaultRuleEngine
from recommendation.rules import build_mvp_rules
from recommendation.types import RecommendationType


def _base_snapshot() -> AnalyticsSnapshot:
    return AnalyticsSnapshot(
        user_id="u-rules",
        project_id=None,
        generated_at=datetime(2026, 4, 21, 12, 0, 0),
        metrics={
            "tx_count": 24.0,
            "total_expense": 2200.0,
            "total_expense_full": 2200.0,
            "total_expense_baseline_adjusted": 2200.0,
            "total_expense_prev_month": 1400.0,
            "total_expense_3m_baseline": 1500.0,
            "spend_forecast": 3100.0,
            "monthly_budget_total": 2400.0,
            "recurring_share": 0.41,
            "recurring_amount": 980.0,
            "recurring_amount_baseline_adjusted": 980.0,
            "small_expense_share": 0.24,
            "small_expense_amount": 720.0,
            "repeated_small_tx_count": 7.0,
            "repeated_small_tx_amount": 380.0,
            "weekend_spend_total": 860.0,
            "weekday_spend_total": 600.0,
            "weekday_vs_weekend_ratio": 1.43,
            "positive_category_reduction": 0.11,
            "outlier_count": 0.0,
        },
        dimensions={
            "category_share_current": {
                "food": 0.36,
                "transport": 0.22,
                "entertainment": 0.18,
            },
            "category_share_prev_month": {
                "food": 0.24,
                "transport": 0.18,
                "entertainment": 0.20,
            },
            "category_share_3m_baseline": {
                "food": 0.23,
                "transport": 0.19,
                "entertainment": 0.18,
            },
        },
        metadata={"positive_reduced_category_key": "entertainment"},
    )


@pytest.mark.asyncio
async def test_mvp_rules_produce_candidates_from_snapshot():
    engine = DefaultRuleEngine(build_mvp_rules())
    snapshot = _base_snapshot()

    candidates = await engine.evaluate(snapshot, RecommendationSettings())
    types = {item.recommendation_type for item in candidates}

    assert RecommendationType.FORECAST_OVERSPEND in types
    assert RecommendationType.TOTAL_GROWTH_VS_PREV_MONTH in types
    assert RecommendationType.CATEGORY_GROWTH_VS_PREV_MONTH in types
    assert RecommendationType.HIGH_RECURRING_SHARE in types
    assert RecommendationType.SMALL_EXPENSES_ACCUMULATION in types
    assert RecommendationType.CASHBACK_OPPORTUNITY in types
    assert RecommendationType.POSITIVE_CATEGORY_REDUCTION in types


@pytest.mark.asyncio
async def test_mvp_rules_filter_small_noisy_values():
    engine = DefaultRuleEngine(build_mvp_rules())
    snapshot = AnalyticsSnapshot(
        user_id="u-small",
        project_id=None,
        generated_at=datetime(2026, 4, 21, 12, 0, 0),
        metrics={
            "tx_count": 3.0,
            "total_expense": 220.0,
            "total_expense_prev_month": 210.0,
            "total_expense_3m_baseline": 205.0,
            "spend_forecast": 240.0,
            "monthly_budget_total": 230.0,
            "small_expense_amount": 80.0,
            "small_expense_share": 0.08,
            "weekend_spend_total": 60.0,
            "weekday_spend_total": 120.0,
            "weekday_vs_weekend_ratio": 0.5,
            "outlier_count": 0.0,
        },
    )

    candidates = await engine.evaluate(snapshot, RecommendationSettings())
    assert candidates == []


@pytest.mark.asyncio
async def test_growth_rules_are_suppressed_when_outlier_distorts_totals():
    engine = DefaultRuleEngine(build_mvp_rules())
    snapshot = _base_snapshot()
    distorted_metrics = dict(snapshot.metrics)
    distorted_metrics.update(
        {
            "outlier_count": 1.0,
            "total_expense_full": 9200.0,
            "total_expense_baseline_adjusted": 2100.0,
        }
    )
    snapshot = AnalyticsSnapshot(
        user_id=snapshot.user_id,
        project_id=snapshot.project_id,
        generated_at=snapshot.generated_at,
        period_start=snapshot.period_start,
        period_end=snapshot.period_end,
        metrics=distorted_metrics,
        dimensions=snapshot.dimensions,
        events=snapshot.events,
        baseline_metrics=snapshot.baseline_metrics,
        adjustments=snapshot.adjustments,
        metadata=snapshot.metadata,
    )

    candidates = await engine.evaluate(snapshot, RecommendationSettings())
    types = {item.recommendation_type for item in candidates}

    assert RecommendationType.FORECAST_OVERSPEND not in types
    assert RecommendationType.TOTAL_GROWTH_VS_PREV_MONTH not in types
    assert RecommendationType.TOTAL_GROWTH_VS_3M_BASELINE not in types
