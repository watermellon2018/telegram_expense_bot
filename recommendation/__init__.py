"""
Recommendation module package.

Contains internal layers for:
- analytics snapshot preparation
- outlier/baseline adjustment
- rules and rule engine
- ranking
- formatting
- repositories (settings/history/feedback)
"""

from recommendation.analytics import AnalyticsService, PreparedAnalyticsService
from recommendation.feedback_service import RecommendationFeedbackService
from recommendation.formatter import DefaultRecommendationFormatter, RecommendationFormatter
from recommendation.models import (
    AnalyticsSnapshot,
    BaselineAdjustment,
    CandidateRecommendation,
    FinalRecommendation,
    RecommendationFeedback,
    RecommendationHistoryEntry,
    RecommendationRecord,
    RecommendationRequest,
    RecommendationSettings,
    UserRecommendationSettings,
    UserRecommendationSettingsUpdate,
    build_default_user_recommendation_settings,
)
from recommendation.outliers import BaselineOutlierHandler, OutlierHandler
from recommendation.pipeline import RecommendationPipeline, build_default_recommendation_pipeline
from recommendation.ranking import RankingService, ScoreRankingService
from recommendation.settings_service import RecommendationSettingsService
from recommendation.rule_engine import DefaultRuleEngine, RuleEngine
from recommendation.types import (
    RECOMMENDATION_FEEDBACK_ACTION_TYPES,
    RECOMMENDATION_FEEDBACK_ACTION_TYPE_VALUES,
    RECOMMENDATION_HISTORY_STATUSES,
    RECOMMENDATION_HISTORY_STATUS_VALUES,
    RECOMMENDATION_TYPES,
    RECOMMENDATION_TYPE_VALUES,
    RecommendationFeedbackActionType,
    RecommendationHistoryStatus,
    RecommendationType,
    parse_recommendation_feedback_action_type,
    parse_recommendation_history_status,
    is_recommendation_type,
    parse_recommendation_type,
)

__all__ = [
    "AnalyticsService",
    "PreparedAnalyticsService",
    "RecommendationFormatter",
    "DefaultRecommendationFormatter",
    "AnalyticsSnapshot",
    "BaselineAdjustment",
    "CandidateRecommendation",
    "FinalRecommendation",
    "RecommendationFeedback",
    "RecommendationFeedbackService",
    "RecommendationHistoryEntry",
    "RecommendationRecord",
    "RecommendationRequest",
    "RecommendationSettings",
    "UserRecommendationSettings",
    "UserRecommendationSettingsUpdate",
    "build_default_user_recommendation_settings",
    "OutlierHandler",
    "BaselineOutlierHandler",
    "RecommendationPipeline",
    "build_default_recommendation_pipeline",
    "RankingService",
    "ScoreRankingService",
    "RuleEngine",
    "DefaultRuleEngine",
    "RecommendationHistoryStatus",
    "RecommendationFeedbackActionType",
    "RECOMMENDATION_FEEDBACK_ACTION_TYPES",
    "RECOMMENDATION_FEEDBACK_ACTION_TYPE_VALUES",
    "RecommendationType",
    "RECOMMENDATION_HISTORY_STATUSES",
    "RECOMMENDATION_HISTORY_STATUS_VALUES",
    "RECOMMENDATION_TYPES",
    "RECOMMENDATION_TYPE_VALUES",
    "parse_recommendation_feedback_action_type",
    "parse_recommendation_history_status",
    "parse_recommendation_type",
    "is_recommendation_type",
    "RecommendationSettingsService",
]
