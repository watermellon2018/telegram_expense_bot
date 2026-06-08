"""
Presentation/formatter layer for recommendations.
"""

from abc import ABC, abstractmethod
from typing import Callable, Dict, List, Mapping, Sequence, Tuple
from uuid import uuid4

from recommendation.models import AnalyticsSnapshot, CandidateRecommendation, FinalRecommendation
from recommendation.types import RecommendationType


class RecommendationFormatter(ABC):
    """Formats ranked candidates to final presentation objects."""

    @abstractmethod
    def format(
        self,
        ranked_candidates: Sequence[CandidateRecommendation],
        snapshot: AnalyticsSnapshot,
    ) -> Sequence[FinalRecommendation]:
        """Return final recommendations."""


class DefaultRecommendationFormatter(RecommendationFormatter):
    """Type-specific formatter with deterministic, concise, number-driven text."""

    _DISTORTION_SENSITIVE_TYPES = {
        RecommendationType.FORECAST_OVERSPEND,
        RecommendationType.TOTAL_GROWTH_VS_PREV_MONTH,
        RecommendationType.TOTAL_GROWTH_VS_3M_BASELINE,
        RecommendationType.CATEGORY_GROWTH_VS_PREV_MONTH,
        RecommendationType.CATEGORY_GROWTH_VS_3M_BASELINE,
    }

    def format(
        self,
        ranked_candidates: Sequence[CandidateRecommendation],
        snapshot: AnalyticsSnapshot,
    ) -> Sequence[FinalRecommendation]:
        results: List[FinalRecommendation] = []

        for index, candidate in enumerate(ranked_candidates, start=1):
            title, message = self._format_candidate(candidate)
            if self._should_add_outlier_note(candidate, snapshot):
                message = (
                    message
                    + "\nПримечание: сравнение может быть искажено, "
                    "так как в прошлом периоде была крупная разовая покупка."
                )
            if candidate.actions:
                message = message + "\nЧто сделать: " + ", ".join(candidate.actions)

            results.append(
                FinalRecommendation(
                    recommendation_id=str(uuid4()),
                    source_rule_id=candidate.rule_id,
                    recommendation_type=candidate.recommendation_type,
                    title=title,
                    message=message,
                    score=candidate.score,
                    rank=index,
                    actions=tuple(candidate.actions),
                    payload=dict(candidate.payload),
                )
            )

        return results

    def _format_candidate(self, candidate: CandidateRecommendation) -> Tuple[str, str]:
        formatter_map: Dict[RecommendationType, Callable[[CandidateRecommendation], Tuple[str, str]]] = {
            RecommendationType.FORECAST_OVERSPEND: self._format_forecast_overspend,
            RecommendationType.TOTAL_GROWTH_VS_PREV_MONTH: self._format_total_growth_prev_month,
            RecommendationType.TOTAL_GROWTH_VS_3M_BASELINE: self._format_total_growth_3m,
            RecommendationType.CATEGORY_GROWTH_VS_PREV_MONTH: self._format_category_growth_prev_month,
            RecommendationType.CATEGORY_GROWTH_VS_3M_BASELINE: self._format_category_growth_3m,
            RecommendationType.HIGH_RECURRING_SHARE: self._format_high_recurring_share,
            RecommendationType.RECURRING_REVIEW: self._format_recurring_review,
            RecommendationType.SMALL_EXPENSES_ACCUMULATION: self._format_small_expenses,
            RecommendationType.CASHBACK_OPPORTUNITY: self._format_cashback,
            RecommendationType.WEEKDAY_SPENDING_PATTERN: self._format_weekday_pattern,
            RecommendationType.POSITIVE_CATEGORY_REDUCTION: self._format_positive_reduction,
        }
        formatter = formatter_map.get(candidate.recommendation_type)
        if formatter is None:
            return candidate.title, candidate.rationale
        return formatter(candidate)

    def _format_forecast_overspend(self, candidate: CandidateRecommendation) -> Tuple[str, str]:
        payload = candidate.payload
        forecast = _number(payload, "forecast")
        limit = _number(payload, "baseline_limit")
        overspend = _number(payload, "overspend_amount")
        overspend_pct = _percent(payload, "overspend_pct")
        return (
            "Риск перерасхода в этом месяце",
            (
                f"Прогноз расходов: {_money(forecast)}. "
                f"Это выше ориентировочного лимита {_money(limit)} на {_money(overspend)} "
                f"({overspend_pct})."
            ),
        )

    def _format_total_growth_prev_month(self, candidate: CandidateRecommendation) -> Tuple[str, str]:
        payload = candidate.payload
        return (
            "Расходы выросли к прошлому месяцу",
            (
                f"Рост составил {_money(_number(payload, 'delta_amount'))} "
                f"({ _percent(payload, 'delta_pct') })."
            ),
        )

    def _format_total_growth_3m(self, candidate: CandidateRecommendation) -> Tuple[str, str]:
        payload = candidate.payload
        return (
            "Расходы выше 3-месячной базы",
            (
                f"Отклонение от устойчивой базы: {_money(_number(payload, 'delta_amount'))} "
                f"({ _percent(payload, 'delta_pct') })."
            ),
        )

    def _format_category_growth_prev_month(self, candidate: CandidateRecommendation) -> Tuple[str, str]:
        return self._format_category_growth(candidate, "Рост категории к прошлому месяцу")

    def _format_category_growth_3m(self, candidate: CandidateRecommendation) -> Tuple[str, str]:
        return self._format_category_growth(candidate, "Категория выше 3-месячной базы")

    def _format_category_growth(
        self,
        candidate: CandidateRecommendation,
        title: str,
    ) -> Tuple[str, str]:
        payload = candidate.payload
        category = str(payload.get("entity_id") or "категория")
        delta_amount = _money(_number(payload, "delta_amount"))
        delta_pct = _percent(payload, "delta_pct")
        return title, f"Категория '{category}' выросла на {delta_amount} ({delta_pct})."

    def _format_high_recurring_share(self, candidate: CandidateRecommendation) -> Tuple[str, str]:
        payload = candidate.payload
        recurring_amount = _money(_number(payload, "recurring_amount"))
        recurring_share = _share_percent(payload, "recurring_share")
        return (
            "Высокая доля регулярных платежей",
            f"Регулярные списания: {recurring_amount} ({recurring_share}) от месячных расходов.",
        )

    def _format_recurring_review(self, candidate: CandidateRecommendation) -> Tuple[str, str]:
        payload = candidate.payload
        recurring_amount = _money(_number(payload, "recurring_amount"))
        recurring_share = _share_percent(payload, "recurring_share")
        return (
            "Есть потенциал оптимизации подписок",
            f"Регулярные траты достигли {recurring_amount} ({recurring_share}). Есть смысл пересмотреть их состав.",
        )

    def _format_small_expenses(self, candidate: CandidateRecommendation) -> Tuple[str, str]:
        payload = candidate.payload
        small_amount = _money(_number(payload, "small_amount"))
        small_share = _share_percent(payload, "small_share")
        repeated_count = int(_number(payload, "repeated_small_tx_count"))
        return (
            "Мелкие траты заметно накапливаются",
            f"Малые покупки: {small_amount} ({small_share}), повторяющихся операций: {repeated_count}.",
        )

    def _format_cashback(self, candidate: CandidateRecommendation) -> Tuple[str, str]:
        payload = candidate.payload
        category = str(payload.get("entity_id") or "категория")
        category_amount = _money(_number(payload, "category_amount"))
        cashback = _money(_number(payload, "estimated_cashback"))
        return (
            "В категории есть потенциал кешбэка",
            f"По категории '{category}' расходы {category_amount}. Потенциальная выгода с кешбэком: около {cashback}.",
        )

    def _format_weekday_pattern(self, candidate: CandidateRecommendation) -> Tuple[str, str]:
        payload = candidate.payload
        weekend = _money(_number(payload, "weekend_spend"))
        weekday = _money(_number(payload, "weekday_spend"))
        ratio = _ratio(payload, "ratio")
        return (
            "На выходных траты выше обычного",
            f"Выходные: {weekend}, будни: {weekday}, соотношение: {ratio}.",
        )

    def _format_positive_reduction(self, candidate: CandidateRecommendation) -> Tuple[str, str]:
        payload = candidate.payload
        category = str(payload.get("entity_id") or "категория")
        reduction = _share_percent(payload, "reduction_share")
        return (
            "Позитивная динамика по категории",
            f"Доля категории '{category}' снизилась на {reduction}.",
        )

    def _should_add_outlier_note(
        self,
        candidate: CandidateRecommendation,
        snapshot: AnalyticsSnapshot,
    ) -> bool:
        if candidate.recommendation_type not in self._DISTORTION_SENSITIVE_TYPES:
            return False

        outlier_count = _metric(snapshot.metrics, "outlier_count")
        if outlier_count <= 0:
            return False

        full_total = _metric(snapshot.metrics, "total_expense_full")
        adjusted_total = _metric(snapshot.metrics, "total_expense_baseline_adjusted")
        if full_total <= 0:
            return False
        distortion = abs(full_total - adjusted_total) / full_total
        return distortion >= 0.25


def _metric(metrics: Mapping[str, object], key: str) -> float:
    value = metrics.get(key, 0.0)
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _number(payload: Mapping[str, object], key: str) -> float:
    value = payload.get(key, 0.0)
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _percent(payload: Mapping[str, object], key: str) -> str:
    return f"{_number(payload, key):.1f}%"


def _share_percent(payload: Mapping[str, object], key: str) -> str:
    value = _number(payload, key)
    if value <= 1.0:
        value *= 100.0
    return f"{value:.1f}%"


def _ratio(payload: Mapping[str, object], key: str) -> str:
    return f"{_number(payload, key):.2f}"


def _money(value: float) -> str:
    rounded = int(round(value))
    return f"{rounded:,}".replace(",", " ")
