from recommendation.models import CandidateRecommendation
from recommendation.types import (
    RECOMMENDATION_FEEDBACK_ACTION_TYPE_VALUES,
    RECOMMENDATION_TYPE_VALUES,
    RECOMMENDATION_TYPES,
    RecommendationType,
    is_recommendation_type,
)


def test_mvp_recommendation_types_are_defined_in_one_source():
    expected = (
        "forecast_overspend",
        "total_growth_vs_prev_month",
        "total_growth_vs_3m_baseline",
        "category_growth_vs_prev_month",
        "category_growth_vs_3m_baseline",
        "high_recurring_share",
        "recurring_review",
        "small_expenses_accumulation",
        "cashback_opportunity",
        "weekday_spending_pattern",
        "positive_category_reduction",
    )
    assert RECOMMENDATION_TYPE_VALUES == expected
    assert tuple(item.value for item in RECOMMENDATION_TYPES) == expected


def test_candidate_recommendation_normalizes_type_to_enum():
    candidate = CandidateRecommendation(
        rule_id="r1",
        recommendation_type="forecast_overspend",
        title="title",
        rationale="reason",
        score=0.5,
    )
    assert candidate.recommendation_type == RecommendationType.FORECAST_OVERSPEND
    assert is_recommendation_type(candidate.recommendation_type.value)


def test_feedback_action_types_are_stable():
    assert RECOMMENDATION_FEEDBACK_ACTION_TYPE_VALUES == (
        "shown",
        "dismissed",
        "liked",
        "disliked",
        "opened_details",
    )
