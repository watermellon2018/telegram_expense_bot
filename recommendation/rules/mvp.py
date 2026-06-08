"""
MVP recommendation rules operating on prepared analytics snapshot only.
"""

from typing import Dict, Mapping, Optional, Sequence, Tuple

from recommendation.models import AnalyticsSnapshot, CandidateRecommendation
from recommendation.rules.base import RecommendationRule
from recommendation.types import RecommendationType


_MIN_HISTORY_TX_COUNT = 5.0
_OUTLIER_DISTORTION_RATIO_THRESHOLD = 0.35


def _metric(snapshot: AnalyticsSnapshot, key: str, default: float = 0.0) -> float:
    value = snapshot.metrics.get(key, default)
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _dimension(snapshot: AnalyticsSnapshot, key: str) -> Mapping[str, float]:
    raw = snapshot.dimensions.get(key) or {}
    if not isinstance(raw, Mapping):
        return {}
    result: Dict[str, float] = {}
    for item_key, value in raw.items():
        try:
            result[str(item_key)] = float(value)
        except (TypeError, ValueError):
            continue
    return result


def _positive_change_percent(change: float, base: float) -> float:
    if base <= 0:
        return 0.0
    return (change / base) * 100.0


def _effective_total_expense(snapshot: AnalyticsSnapshot) -> float:
    adjusted = _metric(snapshot, "total_expense_baseline_adjusted", -1.0)
    if adjusted >= 0:
        return adjusted
    return _metric(snapshot, "total_expense")


def _effective_recurring_amount(snapshot: AnalyticsSnapshot) -> float:
    adjusted = _metric(snapshot, "recurring_amount_baseline_adjusted", -1.0)
    if adjusted >= 0:
        return adjusted
    return _metric(snapshot, "recurring_amount")


def _outlier_distortion_ratio(snapshot: AnalyticsSnapshot) -> float:
    full_value = _metric(snapshot, "total_expense_full", 0.0)
    adjusted_value = _metric(snapshot, "total_expense_baseline_adjusted", full_value)
    if full_value <= 0:
        return 0.0
    return abs(full_value - adjusted_value) / full_value


def _is_outlier_distorted(snapshot: AnalyticsSnapshot) -> bool:
    outlier_count = _metric(snapshot, "outlier_count", 0.0)
    if outlier_count <= 0:
        return False
    return _outlier_distortion_ratio(snapshot) >= _OUTLIER_DISTORTION_RATIO_THRESHOLD


def _has_min_history(snapshot: AnalyticsSnapshot) -> bool:
    return _metric(snapshot, "tx_count", 0.0) >= _MIN_HISTORY_TX_COUNT


class ForecastOverspendRule(RecommendationRule):
    rule_id = RecommendationType.FORECAST_OVERSPEND.value
    priority = 10

    async def evaluate(self, snapshot: AnalyticsSnapshot) -> Sequence[CandidateRecommendation]:
        if not _has_min_history(snapshot) or _is_outlier_distorted(snapshot):
            return tuple()

        forecast = _metric(snapshot, "spend_forecast", 0.0)
        if forecast <= 0:
            return tuple()

        monthly_budget_total = _metric(snapshot, "monthly_budget_total", 0.0)
        if monthly_budget_total <= 0:
            monthly_budget_total = _metric(snapshot, "total_expense_prev_month", 0.0)

        if monthly_budget_total <= 0:
            return tuple()

        overspend_amount = forecast - monthly_budget_total
        overspend_pct = _positive_change_percent(overspend_amount, monthly_budget_total)
        if overspend_amount < 500.0 or overspend_pct < 10.0:
            return tuple()

        score = min(95.0, 55.0 + (overspend_pct * 0.6))
        return (
            CandidateRecommendation(
                rule_id=self.rule_id,
                recommendation_type=RecommendationType.FORECAST_OVERSPEND,
                title="Риск перерасхода в этом месяце",
                rationale=(
                    f"Прогноз расходов {forecast:.0f} выше лимита на {overspend_amount:.0f}"
                    f" ({overspend_pct:.1f}%)."
                ),
                score=score,
                priority=self.priority,
                actions=("Проверь крупные категории", "Скорректируй лимит недели"),
                payload={
                    "forecast": forecast,
                    "baseline_limit": monthly_budget_total,
                    "overspend_amount": overspend_amount,
                    "overspend_pct": overspend_pct,
                    "entity_type": "month",
                },
            ),
        )


class TotalGrowthVsPrevMonthRule(RecommendationRule):
    rule_id = RecommendationType.TOTAL_GROWTH_VS_PREV_MONTH.value
    priority = 20

    async def evaluate(self, snapshot: AnalyticsSnapshot) -> Sequence[CandidateRecommendation]:
        if not _has_min_history(snapshot) or _is_outlier_distorted(snapshot):
            return tuple()

        current_total = _effective_total_expense(snapshot)
        prev_total = _metric(snapshot, "total_expense_prev_month", 0.0)
        if prev_total <= 0:
            return tuple()

        change = current_total - prev_total
        change_pct = _positive_change_percent(change, prev_total)
        if change < 300.0 or change_pct < 12.0:
            return tuple()

        score = min(90.0, 45.0 + (change_pct * 0.7))
        return (
            CandidateRecommendation(
                rule_id=self.rule_id,
                recommendation_type=RecommendationType.TOTAL_GROWTH_VS_PREV_MONTH,
                title="Расходы выросли к прошлому месяцу",
                rationale=(
                    f"Траты увеличились на {change:.0f} ({change_pct:.1f}%)"
                    " относительно прошлого месяца."
                ),
                score=score,
                priority=self.priority,
                actions=("Сверь категории с максимальным ростом",),
                payload={
                    "current_total": current_total,
                    "previous_total": prev_total,
                    "delta_amount": change,
                    "delta_pct": change_pct,
                    "entity_type": "month",
                },
            ),
        )


class TotalGrowthVs3MBaselineRule(RecommendationRule):
    rule_id = RecommendationType.TOTAL_GROWTH_VS_3M_BASELINE.value
    priority = 25

    async def evaluate(self, snapshot: AnalyticsSnapshot) -> Sequence[CandidateRecommendation]:
        if not _has_min_history(snapshot) or _is_outlier_distorted(snapshot):
            return tuple()

        current_total = _effective_total_expense(snapshot)
        baseline_total = _metric(snapshot, "total_expense_3m_baseline", 0.0)
        if baseline_total <= 0:
            return tuple()

        change = current_total - baseline_total
        change_pct = _positive_change_percent(change, baseline_total)
        if change < 300.0 or change_pct < 10.0:
            return tuple()

        score = min(88.0, 42.0 + (change_pct * 0.7))
        return (
            CandidateRecommendation(
                rule_id=self.rule_id,
                recommendation_type=RecommendationType.TOTAL_GROWTH_VS_3M_BASELINE,
                title="Траты выше 3-месячной базы",
                rationale=(
                    f"Расходы на {change:.0f} ({change_pct:.1f}%)"
                    " выше среднего устойчивого уровня."
                ),
                score=score,
                priority=self.priority,
                actions=("Оцени одноразовые и необязательные покупки",),
                payload={
                    "current_total": current_total,
                    "baseline_total": baseline_total,
                    "delta_amount": change,
                    "delta_pct": change_pct,
                    "entity_type": "month",
                },
            ),
        )


class CategoryGrowthVsPrevMonthRule(RecommendationRule):
    rule_id = RecommendationType.CATEGORY_GROWTH_VS_PREV_MONTH.value
    priority = 30

    async def evaluate(self, snapshot: AnalyticsSnapshot) -> Sequence[CandidateRecommendation]:
        return _evaluate_category_growth(
            snapshot=snapshot,
            rule_id=self.rule_id,
            recommendation_type=RecommendationType.CATEGORY_GROWTH_VS_PREV_MONTH,
            baseline_share_key="category_share_prev_month",
            baseline_total_key="total_expense_prev_month",
            title="Рост трат в категории к прошлому месяцу",
        )


class CategoryGrowthVs3MBaselineRule(RecommendationRule):
    rule_id = RecommendationType.CATEGORY_GROWTH_VS_3M_BASELINE.value
    priority = 35

    async def evaluate(self, snapshot: AnalyticsSnapshot) -> Sequence[CandidateRecommendation]:
        return _evaluate_category_growth(
            snapshot=snapshot,
            rule_id=self.rule_id,
            recommendation_type=RecommendationType.CATEGORY_GROWTH_VS_3M_BASELINE,
            baseline_share_key="category_share_3m_baseline",
            baseline_total_key="total_expense_3m_baseline",
            title="Категория вышла выше 3-месячной базы",
        )


def _evaluate_category_growth(
    snapshot: AnalyticsSnapshot,
    rule_id: str,
    recommendation_type: RecommendationType,
    baseline_share_key: str,
    baseline_total_key: str,
    title: str,
) -> Sequence[CandidateRecommendation]:
    if not _has_min_history(snapshot) or _is_outlier_distorted(snapshot):
        return tuple()

    current_total = _effective_total_expense(snapshot)
    baseline_total = _metric(snapshot, baseline_total_key, 0.0)
    if current_total <= 0 or baseline_total <= 0:
        return tuple()

    current_shares = _dimension(snapshot, "category_share_current")
    baseline_shares = _dimension(snapshot, baseline_share_key)
    if not current_shares or not baseline_shares:
        return tuple()

    best_category = None
    best_delta_abs = 0.0
    best_delta_pct = 0.0
    for category_key, current_share in current_shares.items():
        baseline_share = baseline_shares.get(category_key)
        if baseline_share is None:
            continue
        current_amount = current_share * current_total
        baseline_amount = baseline_share * baseline_total
        delta_abs = current_amount - baseline_amount
        delta_pct = _positive_change_percent(delta_abs, baseline_amount)
        if delta_abs > best_delta_abs:
            best_category = category_key
            best_delta_abs = delta_abs
            best_delta_pct = delta_pct

    if best_category is None:
        return tuple()
    if best_delta_abs < 200.0 or best_delta_pct < 15.0:
        return tuple()

    score = min(85.0, 40.0 + (best_delta_pct * 0.6))
    return (
        CandidateRecommendation(
            rule_id=rule_id,
            recommendation_type=recommendation_type,
            title=title,
            rationale=(
                f"Категория '{best_category}' выросла на {best_delta_abs:.0f}"
                f" ({best_delta_pct:.1f}%)."
            ),
            score=score,
            priority=40,
            actions=("Проверь детальные траты категории",),
            payload={
                "entity_type": "category",
                "entity_id": best_category,
                "delta_amount": best_delta_abs,
                "delta_pct": best_delta_pct,
            },
        ),
    )


class HighRecurringShareRule(RecommendationRule):
    rule_id = RecommendationType.HIGH_RECURRING_SHARE.value
    priority = 40

    async def evaluate(self, snapshot: AnalyticsSnapshot) -> Sequence[CandidateRecommendation]:
        if not _has_min_history(snapshot) or _is_outlier_distorted(snapshot):
            return tuple()

        recurring_share = _metric(snapshot, "recurring_share", 0.0)
        recurring_amount = _effective_recurring_amount(snapshot)
        if recurring_amount < 700.0 or recurring_share < 0.35:
            return tuple()

        score = min(82.0, 45.0 + recurring_share * 70.0)
        return (
            CandidateRecommendation(
                rule_id=self.rule_id,
                recommendation_type=RecommendationType.HIGH_RECURRING_SHARE,
                title="Высокая доля регулярных платежей",
                rationale=(
                    f"Регулярные списания занимают {recurring_share * 100:.1f}%"
                    f" ({recurring_amount:.0f}) от расходов."
                ),
                score=score,
                priority=self.priority,
                actions=("Проверь подписки и автоплатежи",),
                payload={
                    "entity_type": "recurring",
                    "recurring_share": recurring_share,
                    "recurring_amount": recurring_amount,
                },
            ),
        )


class RecurringReviewRule(RecommendationRule):
    rule_id = RecommendationType.RECURRING_REVIEW.value
    priority = 45

    async def evaluate(self, snapshot: AnalyticsSnapshot) -> Sequence[CandidateRecommendation]:
        if not _has_min_history(snapshot) or _is_outlier_distorted(snapshot):
            return tuple()

        recurring_amount = _effective_recurring_amount(snapshot)
        recurring_share = _metric(snapshot, "recurring_share", 0.0)
        if recurring_amount < 1000.0 or recurring_share < 0.2:
            return tuple()

        score = min(78.0, 35.0 + recurring_share * 80.0)
        return (
            CandidateRecommendation(
                rule_id=self.rule_id,
                recommendation_type=RecommendationType.RECURRING_REVIEW,
                title="Есть потенциал ревизии регулярных списаний",
                rationale=(
                    f"Сумма регулярных расходов достигла {recurring_amount:.0f}."
                    " Имеет смысл проверить их актуальность."
                ),
                score=score,
                priority=self.priority,
                actions=("Отключи неиспользуемые сервисы", "Пересмотри тарифы"),
                payload={
                    "entity_type": "recurring",
                    "recurring_share": recurring_share,
                    "recurring_amount": recurring_amount,
                },
            ),
        )


class SmallExpensesAccumulationRule(RecommendationRule):
    rule_id = RecommendationType.SMALL_EXPENSES_ACCUMULATION.value
    priority = 50

    async def evaluate(self, snapshot: AnalyticsSnapshot) -> Sequence[CandidateRecommendation]:
        if not _has_min_history(snapshot) or _is_outlier_distorted(snapshot):
            return tuple()

        small_share = _metric(snapshot, "small_expense_share", 0.0)
        small_amount = _metric(snapshot, "small_expense_amount", 0.0)
        repeated_count = _metric(snapshot, "repeated_small_tx_count", 0.0)
        repeated_amount = _metric(snapshot, "repeated_small_tx_amount", 0.0)

        is_large_small_bucket = small_amount >= 600.0 and small_share >= 0.2
        is_repeated_pattern = repeated_count >= 5.0 and repeated_amount >= 300.0
        if not is_large_small_bucket and not is_repeated_pattern:
            return tuple()

        score = min(80.0, 32.0 + (small_share * 80.0) + min(10.0, repeated_count))
        return (
            CandidateRecommendation(
                rule_id=self.rule_id,
                recommendation_type=RecommendationType.SMALL_EXPENSES_ACCUMULATION,
                title="Мелкие траты заметно накапливаются",
                rationale=(
                    f"Малые покупки составили {small_amount:.0f}"
                    f" ({small_share * 100:.1f}%)."
                ),
                score=score,
                priority=self.priority,
                actions=("Поставь лимит на импульсные покупки",),
                payload={
                    "entity_type": "month",
                    "small_amount": small_amount,
                    "small_share": small_share,
                    "repeated_small_tx_count": repeated_count,
                    "repeated_small_tx_amount": repeated_amount,
                },
            ),
        )


class WeekdaySpendingPatternRule(RecommendationRule):
    rule_id = RecommendationType.WEEKDAY_SPENDING_PATTERN.value
    priority = 55

    async def evaluate(self, snapshot: AnalyticsSnapshot) -> Sequence[CandidateRecommendation]:
        if not _has_min_history(snapshot) or _is_outlier_distorted(snapshot):
            return tuple()

        weekend_spend = _metric(snapshot, "weekend_spend_total", 0.0)
        weekday_spend = _metric(snapshot, "weekday_spend_total", 0.0)
        ratio = _metric(snapshot, "weekday_vs_weekend_ratio", 0.0)

        if weekend_spend < 400.0 or ratio < 1.2:
            return tuple()

        score = min(76.0, 34.0 + ratio * 18.0)
        return (
            CandidateRecommendation(
                rule_id=self.rule_id,
                recommendation_type=RecommendationType.WEEKDAY_SPENDING_PATTERN,
                title="На выходных траты выше обычного",
                rationale=(
                    f"За выходные потрачено {weekend_spend:.0f},"
                    f" соотношение к будням {ratio:.2f}."
                ),
                score=score,
                priority=self.priority,
                actions=("Запланируй лимит на выходные",),
                payload={
                    "entity_type": "month",
                    "weekend_spend": weekend_spend,
                    "weekday_spend": weekday_spend,
                    "ratio": ratio,
                },
            ),
        )


class CashbackOpportunityRule(RecommendationRule):
    rule_id = RecommendationType.CASHBACK_OPPORTUNITY.value
    priority = 60

    async def evaluate(self, snapshot: AnalyticsSnapshot) -> Sequence[CandidateRecommendation]:
        if not _has_min_history(snapshot) or _is_outlier_distorted(snapshot):
            return tuple()

        total_expense = _effective_total_expense(snapshot)
        category_shares = _dimension(snapshot, "category_share_current")
        if total_expense <= 0 or not category_shares:
            return tuple()

        best_category, best_share = max(category_shares.items(), key=lambda pair: pair[1])
        category_amount = best_share * total_expense
        if category_amount < 700.0 or best_share < 0.18:
            return tuple()

        estimated_cashback = category_amount * 0.02
        score = min(74.0, 30.0 + best_share * 110.0)
        return (
            CandidateRecommendation(
                rule_id=self.rule_id,
                recommendation_type=RecommendationType.CASHBACK_OPPORTUNITY,
                title="В категории есть потенциал кешбэка",
                rationale=(
                    f"В категории '{best_category}' расходы {category_amount:.0f};"
                    f" возможная выгода около {estimated_cashback:.0f}."
                ),
                score=score,
                priority=self.priority,
                actions=("Проверь карту с повышенным кешбэком",),
                payload={
                    "entity_type": "category",
                    "entity_id": best_category,
                    "category_share": best_share,
                    "category_amount": category_amount,
                    "estimated_cashback": estimated_cashback,
                },
            ),
        )


class PositiveCategoryReductionRule(RecommendationRule):
    rule_id = RecommendationType.POSITIVE_CATEGORY_REDUCTION.value
    priority = 70

    async def evaluate(self, snapshot: AnalyticsSnapshot) -> Sequence[CandidateRecommendation]:
        if not _has_min_history(snapshot) or _is_outlier_distorted(snapshot):
            return tuple()

        reduction_share = _metric(snapshot, "positive_category_reduction", 0.0)
        if reduction_share < 0.05:
            return tuple()

        category_key = str(snapshot.metadata.get("positive_reduced_category_key") or "")
        if not category_key:
            return tuple()

        score = min(72.0, 28.0 + reduction_share * 140.0)
        return (
            CandidateRecommendation(
                rule_id=self.rule_id,
                recommendation_type=RecommendationType.POSITIVE_CATEGORY_REDUCTION,
                title="Позитивная динамика по категории",
                rationale=(
                    f"Доля категории '{category_key}' снизилась на"
                    f" {reduction_share * 100:.1f}%."
                ),
                score=score,
                priority=self.priority,
                actions=("Продолжай текущую стратегию",),
                payload={
                    "entity_type": "category",
                    "entity_id": category_key,
                    "reduction_share": reduction_share,
                },
            ),
        )


def build_mvp_rules() -> Tuple[RecommendationRule, ...]:
    """Return deterministic MVP ruleset in stable order."""
    return (
        ForecastOverspendRule(),
        TotalGrowthVsPrevMonthRule(),
        TotalGrowthVs3MBaselineRule(),
        CategoryGrowthVsPrevMonthRule(),
        CategoryGrowthVs3MBaselineRule(),
        HighRecurringShareRule(),
        RecurringReviewRule(),
        SmallExpensesAccumulationRule(),
        WeekdaySpendingPatternRule(),
        CashbackOpportunityRule(),
        PositiveCategoryReductionRule(),
    )
