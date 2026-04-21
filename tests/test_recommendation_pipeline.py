import pytest

from recommendation.analytics import PreparedAnalyticsService
from recommendation.formatter import DefaultRecommendationFormatter
from recommendation.models import CandidateRecommendation, RecommendationRequest, RecommendationSettings
from recommendation.outliers import BaselineOutlierHandler
from recommendation.pipeline import RecommendationPipeline
from recommendation.ranking import ScoreRankingService
from recommendation.repositories.in_memory import (
    InMemoryFeedbackRepository,
    InMemoryHistoryRepository,
    InMemorySettingsRepository,
)
from recommendation.rule_engine import DefaultRuleEngine
from recommendation.rules.base import RecommendationRule
from recommendation.types import RecommendationType


class CaptureMetricRule(RecommendationRule):
    rule_id = "capture_metric_rule"
    priority = 10

    def __init__(self):
        self.last_snapshot = None

    async def evaluate(self, snapshot):
        self.last_snapshot = snapshot
        score = float(snapshot.metrics.get("monthly_spend", 0.0))
        return [
            CandidateRecommendation(
                rule_id=self.rule_id,
                recommendation_type=RecommendationType.FORECAST_OVERSPEND,
                title="Cap spend",
                rationale="Detected high spend",
                score=score,
            )
        ]


class StaticRule(RecommendationRule):
    def __init__(self, rule_id, score, priority=100):
        self.rule_id = rule_id
        self.priority = priority
        self._score = score

    async def evaluate(self, snapshot):
        return [
            CandidateRecommendation(
                rule_id=self.rule_id,
                recommendation_type=RecommendationType.CASHBACK_OPPORTUNITY,
                title=self.rule_id,
                rationale="candidate",
                score=self._score,
                priority=self.priority,
            )
        ]


async def _build_pipeline(
    rules,
    settings_repository=None,
    history_repository=None,
):
    settings_repo = settings_repository or InMemorySettingsRepository()
    history_repo = history_repository or InMemoryHistoryRepository()
    pipeline = RecommendationPipeline(
        analytics_service=PreparedAnalyticsService(),
        outlier_handler=BaselineOutlierHandler(metric_caps={"monthly_spend": 100.0}),
        rule_engine=DefaultRuleEngine(rules),
        ranking_service=ScoreRankingService(),
        formatter=DefaultRecommendationFormatter(),
        settings_repository=settings_repo,
        history_repository=history_repo,
        feedback_repository=InMemoryFeedbackRepository(),
    )
    return pipeline, settings_repo, history_repo


@pytest.mark.asyncio
async def test_rules_receive_prepared_snapshot_without_direct_sql():
    rule = CaptureMetricRule()
    pipeline, _, _ = await _build_pipeline([rule])

    request = RecommendationRequest(
        user_id="42",
        metrics={"monthly_spend": 250.0},
    )
    result = await pipeline.generate(request)

    assert result
    assert rule.last_snapshot is not None
    assert rule.last_snapshot.metrics["monthly_spend"] == 100.0
    assert rule.last_snapshot.adjustments


@pytest.mark.asyncio
async def test_rule_overrides_are_applied_by_engine():
    enabled_rule = StaticRule("enabled", score=0.9)
    disabled_rule = StaticRule("disabled", score=0.99)
    settings_repo = InMemorySettingsRepository()
    await settings_repo.set_settings(
        user_id="100",
        project_id=None,
        settings=RecommendationSettings(
            enabled=True,
            max_recommendations=3,
            min_score=0.0,
            rule_overrides={"disabled": False},
        ),
    )

    pipeline, _, _ = await _build_pipeline(
        [disabled_rule, enabled_rule],
        settings_repository=settings_repo,
    )

    result = await pipeline.generate(RecommendationRequest(user_id="100"))
    assert len(result) == 1
    assert result[0].source_rule_id == "enabled"


@pytest.mark.asyncio
async def test_ranking_limit_and_history_persistence():
    high = StaticRule("high", score=0.8, priority=20)
    low = StaticRule("low", score=0.3, priority=10)
    settings_repo = InMemorySettingsRepository()
    history_repo = InMemoryHistoryRepository()
    await settings_repo.set_settings(
        user_id="7",
        project_id=None,
        settings=RecommendationSettings(
            enabled=True,
            max_recommendations=1,
            min_score=0.5,
        ),
    )

    pipeline, _, _ = await _build_pipeline(
        [low, high],
        settings_repository=settings_repo,
        history_repository=history_repo,
    )

    result = await pipeline.generate(RecommendationRequest(user_id="7"))
    assert len(result) == 1
    assert result[0].source_rule_id == "high"

    history = await history_repo.get_recent(user_id="7", project_id=None)
    assert len(history) == 1
    assert history[0].source_rule_id == "high"
