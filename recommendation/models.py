"""
Core DTO/dataclass models for recommendation module.
"""

from dataclasses import dataclass, field, replace
from datetime import date, datetime
from typing import Any, Iterable, Mapping, Optional, Sequence, Tuple

from recommendation.types import (
    RecommendationFeedbackActionType,
    RecommendationHistoryStatus,
    RecommendationType,
    parse_recommendation_feedback_action_type,
    parse_recommendation_history_status,
    parse_recommendation_type,
)


def _normalize_recommendation_types(
    values: Optional[Iterable[Any]],
) -> Tuple[RecommendationType, ...]:
    if not values:
        return tuple()

    normalized = []
    seen = set()
    for value in values:
        if isinstance(value, RecommendationType):
            parsed = value
        else:
            try:
                parsed = parse_recommendation_type(str(value))
            except ValueError:
                continue

        if parsed in seen:
            continue
        seen.add(parsed)
        normalized.append(parsed)

    return tuple(normalized)


def _normalize_history_status(value: Any) -> RecommendationHistoryStatus:
    if isinstance(value, RecommendationHistoryStatus):
        return value
    return parse_recommendation_history_status(str(value))


@dataclass(frozen=True)
class RecommendationRequest:
    """Input payload for recommendation generation."""

    user_id: str
    project_id: Optional[int] = None
    requested_at: datetime = field(default_factory=datetime.utcnow)
    period_start: Optional[date] = None
    period_end: Optional[date] = None
    metrics: Mapping[str, float] = field(default_factory=dict)
    dimensions: Mapping[str, Mapping[str, float]] = field(default_factory=dict)
    events: Sequence[Mapping[str, Any]] = field(default_factory=tuple)
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RecommendationSettings:
    """Runtime settings consumed by recommendation layers."""

    enabled: bool = True
    max_recommendations: int = 3
    min_score: float = 0.0
    rule_overrides: Mapping[str, bool] = field(default_factory=dict)
    show_positive_recommendations: bool = True
    hidden_recommendation_types: Sequence[RecommendationType] = field(default_factory=tuple)
    monthly_budget_total: Optional[float] = None

    def __post_init__(self):
        object.__setattr__(
            self,
            "hidden_recommendation_types",
            _normalize_recommendation_types(self.hidden_recommendation_types),
        )
        if self.max_recommendations < 1:
            object.__setattr__(self, "max_recommendations", 1)
        if self.monthly_budget_total is not None:
            object.__setattr__(self, "monthly_budget_total", float(self.monthly_budget_total))

    @classmethod
    def from_user_settings(
        cls,
        user_settings: "UserRecommendationSettings",
    ) -> "RecommendationSettings":
        return cls(
            enabled=user_settings.recommendations_enabled,
            max_recommendations=user_settings.max_recommendations_per_request,
            show_positive_recommendations=user_settings.show_positive_recommendations,
            hidden_recommendation_types=user_settings.hidden_recommendation_types,
            monthly_budget_total=user_settings.monthly_budget_total,
        )


@dataclass(frozen=True)
class UserRecommendationSettingsUpdate:
    """Patch payload for user recommendation settings."""

    recommendations_enabled: Optional[bool] = None
    max_recommendations_per_request: Optional[int] = None
    show_positive_recommendations: Optional[bool] = None
    hidden_recommendation_types: Optional[Sequence[RecommendationType]] = None
    monthly_budget_total: Optional[float] = None
    clear_monthly_budget_total: bool = False

    def __post_init__(self):
        if self.max_recommendations_per_request is not None:
            normalized = max(1, int(self.max_recommendations_per_request))
            object.__setattr__(self, "max_recommendations_per_request", normalized)
        if self.hidden_recommendation_types is not None:
            object.__setattr__(
                self,
                "hidden_recommendation_types",
                _normalize_recommendation_types(self.hidden_recommendation_types),
            )
        if self.monthly_budget_total is not None:
            object.__setattr__(self, "monthly_budget_total", float(self.monthly_budget_total))


@dataclass(frozen=True)
class UserRecommendationSettings:
    """User-level persisted recommendation settings."""

    id: Optional[int]
    user_id: str
    recommendations_enabled: bool = True
    max_recommendations_per_request: int = 3
    show_positive_recommendations: bool = True
    hidden_recommendation_types: Sequence[RecommendationType] = field(default_factory=tuple)
    monthly_budget_total: Optional[float] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    def __post_init__(self):
        object.__setattr__(
            self,
            "hidden_recommendation_types",
            _normalize_recommendation_types(self.hidden_recommendation_types),
        )
        if self.max_recommendations_per_request < 1:
            object.__setattr__(self, "max_recommendations_per_request", 1)
        if self.monthly_budget_total is not None:
            object.__setattr__(self, "monthly_budget_total", float(self.monthly_budget_total))

    def to_runtime_settings(self) -> RecommendationSettings:
        return RecommendationSettings.from_user_settings(self)

    def apply_update(
        self,
        update: UserRecommendationSettingsUpdate,
    ) -> "UserRecommendationSettings":
        next_budget = self.monthly_budget_total
        if update.clear_monthly_budget_total:
            next_budget = None
        elif update.monthly_budget_total is not None:
            next_budget = update.monthly_budget_total

        return replace(
            self,
            recommendations_enabled=(
                self.recommendations_enabled
                if update.recommendations_enabled is None
                else update.recommendations_enabled
            ),
            max_recommendations_per_request=(
                self.max_recommendations_per_request
                if update.max_recommendations_per_request is None
                else update.max_recommendations_per_request
            ),
            show_positive_recommendations=(
                self.show_positive_recommendations
                if update.show_positive_recommendations is None
                else update.show_positive_recommendations
            ),
            hidden_recommendation_types=(
                self.hidden_recommendation_types
                if update.hidden_recommendation_types is None
                else update.hidden_recommendation_types
            ),
            monthly_budget_total=next_budget,
        )


def build_default_user_recommendation_settings(user_id: str) -> UserRecommendationSettings:
    """Build defaults when settings row is missing."""
    return UserRecommendationSettings(
        id=None,
        user_id=user_id,
        recommendations_enabled=True,
        max_recommendations_per_request=3,
        show_positive_recommendations=True,
        hidden_recommendation_types=tuple(),
        monthly_budget_total=None,
        created_at=None,
        updated_at=None,
    )


@dataclass(frozen=True)
class BaselineAdjustment:
    """Single baseline/outlier correction metadata item."""

    metric_key: str
    original_value: float
    adjusted_value: float
    reason: str


@dataclass(frozen=True)
class AnalyticsSnapshot:
    """Prepared analytics snapshot consumed by rules."""

    user_id: str
    project_id: Optional[int]
    generated_at: datetime
    period_start: Optional[date] = None
    period_end: Optional[date] = None
    metrics: Mapping[str, float] = field(default_factory=dict)
    dimensions: Mapping[str, Mapping[str, float]] = field(default_factory=dict)
    events: Sequence[Mapping[str, Any]] = field(default_factory=tuple)
    baseline_metrics: Mapping[str, float] = field(default_factory=dict)
    adjustments: Sequence[BaselineAdjustment] = field(default_factory=tuple)
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CandidateRecommendation:
    """Rule-level recommendation candidate before ranking/formatting."""

    rule_id: str
    recommendation_type: RecommendationType
    title: str
    rationale: str
    score: float
    priority: int = 100
    actions: Sequence[str] = field(default_factory=tuple)
    payload: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if isinstance(self.recommendation_type, RecommendationType):
            return
        object.__setattr__(
            self,
            "recommendation_type",
            parse_recommendation_type(str(self.recommendation_type)),
        )


@dataclass(frozen=True)
class FinalRecommendation:
    """Final recommendation ready for presentation layer."""

    recommendation_id: str
    source_rule_id: str
    recommendation_type: RecommendationType
    title: str
    message: str
    score: float
    rank: int
    actions: Sequence[str] = field(default_factory=tuple)
    payload: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if isinstance(self.recommendation_type, RecommendationType):
            return
        object.__setattr__(
            self,
            "recommendation_type",
            parse_recommendation_type(str(self.recommendation_type)),
        )


@dataclass(frozen=True)
class RecommendationRecord:
    """History record for presented recommendation."""

    recommendation_id: str
    user_id: str
    project_id: Optional[int]
    source_rule_id: str
    recommendation_type: RecommendationType
    score: float
    presented_at: datetime
    payload: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if isinstance(self.recommendation_type, RecommendationType):
            return
        object.__setattr__(
            self,
            "recommendation_type",
            parse_recommendation_type(str(self.recommendation_type)),
        )


@dataclass(frozen=True)
class RecommendationHistoryEntry:
    """Persisted recommendation history row."""

    id: Optional[int]
    user_id: str
    recommendation_type: RecommendationType
    period_key: str
    entity_type: Optional[str] = None
    entity_id: Optional[str] = None
    payload_json: Mapping[str, Any] = field(default_factory=dict)
    score: float = 0.0
    status: RecommendationHistoryStatus = RecommendationHistoryStatus.GENERATED
    generated_at: datetime = field(default_factory=datetime.utcnow)
    shown_at: Optional[datetime] = None

    def __post_init__(self):
        if not isinstance(self.recommendation_type, RecommendationType):
            object.__setattr__(
                self,
                "recommendation_type",
                parse_recommendation_type(str(self.recommendation_type)),
            )
        object.__setattr__(self, "status", _normalize_history_status(self.status))
        object.__setattr__(self, "score", float(self.score))


@dataclass(frozen=True)
class RecommendationFeedback:
    """User feedback entry for previously shown recommendation."""

    recommendation_id: str
    user_id: str
    action_type: RecommendationFeedbackActionType
    id: Optional[int] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    metadata_json: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not isinstance(self.action_type, RecommendationFeedbackActionType):
            object.__setattr__(
                self,
                "action_type",
                parse_recommendation_feedback_action_type(str(self.action_type)),
            )
        object.__setattr__(self, "metadata_json", dict(self.metadata_json))
