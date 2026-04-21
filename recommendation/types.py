"""
Recommendation type definitions (single source of truth).
"""

from enum import Enum
from typing import Tuple


class RecommendationType(str, Enum):
    """Machine-friendly recommendation types for MVP."""

    FORECAST_OVERSPEND = "forecast_overspend"
    TOTAL_GROWTH_VS_PREV_MONTH = "total_growth_vs_prev_month"
    TOTAL_GROWTH_VS_3M_BASELINE = "total_growth_vs_3m_baseline"
    CATEGORY_GROWTH_VS_PREV_MONTH = "category_growth_vs_prev_month"
    CATEGORY_GROWTH_VS_3M_BASELINE = "category_growth_vs_3m_baseline"
    HIGH_RECURRING_SHARE = "high_recurring_share"
    RECURRING_REVIEW = "recurring_review"
    SMALL_EXPENSES_ACCUMULATION = "small_expenses_accumulation"
    CASHBACK_OPPORTUNITY = "cashback_opportunity"
    WEEKDAY_SPENDING_PATTERN = "weekday_spending_pattern"
    POSITIVE_CATEGORY_REDUCTION = "positive_category_reduction"


class RecommendationHistoryStatus(str, Enum):
    """Lifecycle statuses for recommendation history records."""

    GENERATED = "generated"
    SHOWN = "shown"


class RecommendationFeedbackActionType(str, Enum):
    """Feedback event actions for recommendations."""

    SHOWN = "shown"
    DISMISSED = "dismissed"
    LIKED = "liked"
    DISLIKED = "disliked"
    OPENED_DETAILS = "opened_details"


RECOMMENDATION_TYPES: Tuple[RecommendationType, ...] = tuple(RecommendationType)
RECOMMENDATION_TYPE_VALUES: Tuple[str, ...] = tuple(item.value for item in RecommendationType)
RECOMMENDATION_HISTORY_STATUSES: Tuple[RecommendationHistoryStatus, ...] = tuple(
    RecommendationHistoryStatus
)
RECOMMENDATION_HISTORY_STATUS_VALUES: Tuple[str, ...] = tuple(
    item.value for item in RecommendationHistoryStatus
)
RECOMMENDATION_FEEDBACK_ACTION_TYPES: Tuple[RecommendationFeedbackActionType, ...] = tuple(
    RecommendationFeedbackActionType
)
RECOMMENDATION_FEEDBACK_ACTION_TYPE_VALUES: Tuple[str, ...] = tuple(
    item.value for item in RecommendationFeedbackActionType
)


def parse_recommendation_type(value: str) -> RecommendationType:
    """Convert raw value into enum value."""
    return RecommendationType(value)


def is_recommendation_type(value: str) -> bool:
    """Validate recommendation type value."""
    return value in RECOMMENDATION_TYPE_VALUES


def parse_recommendation_history_status(value: str) -> RecommendationHistoryStatus:
    """Convert raw value into history status enum value."""
    return RecommendationHistoryStatus(value)


def parse_recommendation_feedback_action_type(value: str) -> RecommendationFeedbackActionType:
    """Convert raw value into feedback action enum value."""
    return RecommendationFeedbackActionType(value)
