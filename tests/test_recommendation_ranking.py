from datetime import datetime, timedelta

from recommendation.models import (
    AnalyticsSnapshot,
    CandidateRecommendation,
    RecommendationRecord,
    RecommendationSettings,
)
from recommendation.ranking import ScoreRankingService
from recommendation.types import RecommendationType


def _snapshot(tx_count=20.0, full_total=2500.0, adjusted_total=2500.0) -> AnalyticsSnapshot:
    return AnalyticsSnapshot(
        user_id="u-rank",
        project_id=None,
        generated_at=datetime(2026, 4, 21, 12, 0, 0),
        metrics={
            "tx_count": tx_count,
            "total_expense_full": full_total,
            "total_expense_baseline_adjusted": adjusted_total,
        },
    )


def test_ranking_deduplicates_and_returns_top_n():
    service = ScoreRankingService()
    settings = RecommendationSettings(max_recommendations=3)
    snapshot = _snapshot()

    candidates = [
        CandidateRecommendation(
            rule_id="forecast",
            recommendation_type=RecommendationType.FORECAST_OVERSPEND,
            title="forecast",
            rationale="r",
            score=80.0,
            payload={"overspend_pct": 28.0, "overspend_amount": 900.0, "entity_type": "month"},
        ),
        CandidateRecommendation(
            rule_id="growth_prev",
            recommendation_type=RecommendationType.TOTAL_GROWTH_VS_PREV_MONTH,
            title="growth",
            rationale="r",
            score=78.0,
            payload={"delta_pct": 22.0, "delta_amount": 700.0, "entity_type": "month"},
        ),
        CandidateRecommendation(
            rule_id="cat_growth",
            recommendation_type=RecommendationType.CATEGORY_GROWTH_VS_PREV_MONTH,
            title="cat",
            rationale="r",
            score=72.0,
            payload={"delta_pct": 30.0, "delta_amount": 650.0, "entity_type": "category", "entity_id": "food"},
        ),
        CandidateRecommendation(
            rule_id="cashback",
            recommendation_type=RecommendationType.CASHBACK_OPPORTUNITY,
            title="cashback",
            rationale="r",
            score=65.0,
            payload={"category_share": 0.35, "category_amount": 1200.0, "entity_type": "category", "entity_id": "food"},
        ),
        CandidateRecommendation(
            rule_id="small",
            recommendation_type=RecommendationType.SMALL_EXPENSES_ACCUMULATION,
            title="small",
            rationale="r",
            score=60.0,
            payload={"small_share": 0.25, "small_amount": 700.0, "entity_type": "month"},
        ),
    ]

    ranked = service.rank(candidates=candidates, settings=settings, snapshot=snapshot)
    assert len(ranked) == 3

    growth_types = {
        RecommendationType.FORECAST_OVERSPEND,
        RecommendationType.TOTAL_GROWTH_VS_PREV_MONTH,
        RecommendationType.TOTAL_GROWTH_VS_3M_BASELINE,
    }
    assert len([item for item in ranked if item.recommendation_type in growth_types]) == 1

    category_food = [
        item
        for item in ranked
        if item.payload.get("entity_type") == "category" and item.payload.get("entity_id") == "food"
    ]
    assert len(category_food) == 1


def test_novelty_penalty_lowers_repeated_entity_score():
    service = ScoreRankingService()
    settings = RecommendationSettings(max_recommendations=3)
    snapshot = _snapshot()

    repeated = CandidateRecommendation(
        rule_id="cashback_food",
        recommendation_type=RecommendationType.CASHBACK_OPPORTUNITY,
        title="food",
        rationale="r",
        score=70.0,
        payload={"category_share": 0.30, "category_amount": 1100.0, "entity_type": "category", "entity_id": "food"},
    )
    novel = CandidateRecommendation(
        rule_id="cashback_transport",
        recommendation_type=RecommendationType.CASHBACK_OPPORTUNITY,
        title="transport",
        rationale="r",
        score=70.0,
        payload={"category_share": 0.30, "category_amount": 1100.0, "entity_type": "category", "entity_id": "transport"},
    )

    history = [
        RecommendationRecord(
            recommendation_id="r1",
            user_id="u-rank",
            project_id=None,
            source_rule_id="cashback_food",
            recommendation_type=RecommendationType.CASHBACK_OPPORTUNITY,
            score=50.0,
            presented_at=snapshot.generated_at - timedelta(days=2),
            payload={"entity_type": "category", "entity_id": "food"},
        )
    ]

    ranked = service.rank(
        candidates=[repeated, novel],
        settings=settings,
        snapshot=snapshot,
        recent_history=history,
    )

    assert ranked[0].rule_id == "cashback_transport"


def test_confidence_component_depends_on_data_quality():
    service = ScoreRankingService()
    settings = RecommendationSettings(max_recommendations=3)

    candidate = CandidateRecommendation(
        rule_id="growth",
        recommendation_type=RecommendationType.TOTAL_GROWTH_VS_PREV_MONTH,
        title="growth",
        rationale="r",
        score=70.0,
        payload={"delta_pct": 20.0, "delta_amount": 600.0, "entity_type": "month"},
    )

    high_quality = _snapshot(tx_count=30.0, full_total=2400.0, adjusted_total=2400.0)
    low_quality = _snapshot(tx_count=3.0, full_total=6000.0, adjusted_total=1600.0)

    high_ranked = service.rank([candidate], settings=settings, snapshot=high_quality)
    low_ranked = service.rank([candidate], settings=settings, snapshot=low_quality)

    assert high_ranked[0].score > low_ranked[0].score
