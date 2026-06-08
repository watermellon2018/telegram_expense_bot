from datetime import datetime

from recommendation.formatter import DefaultRecommendationFormatter
from recommendation.models import AnalyticsSnapshot, CandidateRecommendation
from recommendation.types import RecommendationType


def _snapshot(outlier_count=0.0, full_total=2000.0, adjusted_total=2000.0):
    return AnalyticsSnapshot(
        user_id="u-format",
        project_id=None,
        generated_at=datetime(2026, 4, 21, 12, 0, 0),
        metrics={
            "outlier_count": outlier_count,
            "total_expense_full": full_total,
            "total_expense_baseline_adjusted": adjusted_total,
        },
    )


def test_formatter_supports_all_mvp_recommendation_types():
    formatter = DefaultRecommendationFormatter()
    snapshot = _snapshot()

    candidates = [
        CandidateRecommendation(
            rule_id=item.value,
            recommendation_type=item,
            title="raw-title",
            rationale="raw-rationale",
            score=50.0,
            actions=("a1",),
            payload={
                "entity_type": "category",
                "entity_id": "food",
                "forecast": 3000.0,
                "baseline_limit": 2400.0,
                "overspend_amount": 600.0,
                "overspend_pct": 25.0,
                "delta_amount": 500.0,
                "delta_pct": 20.0,
                "recurring_amount": 900.0,
                "recurring_share": 0.34,
                "small_amount": 650.0,
                "small_share": 0.23,
                "repeated_small_tx_count": 6.0,
                "category_amount": 1100.0,
                "estimated_cashback": 22.0,
                "weekend_spend": 800.0,
                "weekday_spend": 560.0,
                "ratio": 1.42,
                "reduction_share": 0.08,
            },
        )
        for item in RecommendationType
    ]

    final_items = formatter.format(candidates, snapshot)
    assert len(final_items) == len(RecommendationType)
    for item in final_items:
        assert item.title
        assert item.message
        assert "a1" in item.message


def test_formatter_adds_outlier_limitation_note_for_distorted_comparison():
    formatter = DefaultRecommendationFormatter()
    snapshot = _snapshot(outlier_count=1.0, full_total=9000.0, adjusted_total=2400.0)
    candidate = CandidateRecommendation(
        rule_id=RecommendationType.TOTAL_GROWTH_VS_PREV_MONTH.value,
        recommendation_type=RecommendationType.TOTAL_GROWTH_VS_PREV_MONTH,
        title="x",
        rationale="x",
        score=70.0,
        payload={"delta_amount": 700.0, "delta_pct": 25.0},
    )

    formatted = formatter.format([candidate], snapshot)
    assert len(formatted) == 1
    assert "крупная разовая покупка" in formatted[0].message
