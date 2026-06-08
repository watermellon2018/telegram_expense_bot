"""Rules package for recommendation module."""

from recommendation.rules.base import RecommendationRule
from recommendation.rules.mvp import (
    CashbackOpportunityRule,
    CategoryGrowthVs3MBaselineRule,
    CategoryGrowthVsPrevMonthRule,
    ForecastOverspendRule,
    HighRecurringShareRule,
    PositiveCategoryReductionRule,
    RecurringReviewRule,
    SmallExpensesAccumulationRule,
    TotalGrowthVs3MBaselineRule,
    TotalGrowthVsPrevMonthRule,
    WeekdaySpendingPatternRule,
    build_mvp_rules,
)

__all__ = [
    "RecommendationRule",
    "ForecastOverspendRule",
    "TotalGrowthVsPrevMonthRule",
    "TotalGrowthVs3MBaselineRule",
    "CategoryGrowthVsPrevMonthRule",
    "CategoryGrowthVs3MBaselineRule",
    "HighRecurringShareRule",
    "RecurringReviewRule",
    "SmallExpensesAccumulationRule",
    "WeekdaySpendingPatternRule",
    "CashbackOpportunityRule",
    "PositiveCategoryReductionRule",
    "build_mvp_rules",
]
