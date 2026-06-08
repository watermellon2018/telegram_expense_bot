"""
Outlier handling / baseline adjustment layer.
"""

from abc import ABC, abstractmethod
from dataclasses import replace
from statistics import median
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from recommendation.models import AnalyticsSnapshot, AnalyticsTransaction, BaselineAdjustment


class OutlierHandler(ABC):
    """Adjusts outliers and updates baseline values."""

    @abstractmethod
    async def adjust(self, snapshot: AnalyticsSnapshot) -> AnalyticsSnapshot:
        """Return adjusted snapshot."""


class BaselineOutlierHandler(OutlierHandler):
    """
    Basic metric clipping handler.

    `metric_caps` maps metric key -> max allowed value.
    """

    def __init__(self, metric_caps: Optional[Mapping[str, float]] = None):
        self._metric_caps = dict(metric_caps or {})
        self._detector = OutlierDetectionService()
        self._baseline_builder = BaselineMetricsBuilder()

    async def adjust(self, snapshot: AnalyticsSnapshot) -> AnalyticsSnapshot:
        adjusted_metrics: Dict[str, float] = dict(snapshot.metrics)
        adjusted_baseline_metrics: Dict[str, float] = dict(snapshot.baseline_metrics)
        adjustments: Tuple[BaselineAdjustment, ...] = tuple(snapshot.adjustments)
        collected = []

        if self._metric_caps:
            for metric_key, cap in self._metric_caps.items():
                current = adjusted_metrics.get(metric_key)
                if current is None or current <= cap:
                    continue

                adjusted_metrics[metric_key] = cap
                collected.append(
                    BaselineAdjustment(
                        metric_key=metric_key,
                        original_value=current,
                        adjusted_value=cap,
                        reason="metric_cap",
                    )
                )

        transactions = [_event_to_transaction(event) for event in snapshot.events]
        transactions = [item for item in transactions if item is not None]
        if not transactions and not collected:
            return snapshot

        flagged = self._detector.detect(transactions)
        baseline_metrics = self._baseline_builder.build(flagged)
        adjusted_metrics.update(baseline_metrics)
        adjusted_baseline_metrics.update(baseline_metrics)

        for index, item in enumerate(flagged):
            if not item.is_large_one_time_purchase:
                continue
            collected.append(
                BaselineAdjustment(
                    metric_key=f"event_amount:{index}",
                    original_value=item.amount,
                    adjusted_value=0.0,
                    reason=f"outlier:{item.outlier_flag_source or 'detected'}",
                )
            )

        metadata = dict(snapshot.metadata)
        metadata["outlier_events"] = [
            {
                "amount": item.amount,
                "category_id": item.category_id,
                "is_recurring": item.is_recurring,
                "is_large_one_time_purchase": item.is_large_one_time_purchase,
                "outlier_score": item.outlier_score,
                "outlier_flag_source": item.outlier_flag_source,
            }
            for item in flagged
        ]

        return replace(
            snapshot,
            metrics=adjusted_metrics,
            baseline_metrics=adjusted_baseline_metrics,
            adjustments=adjustments + tuple(collected),
            metadata=metadata,
        )


class OutlierDetectionService:
    """
    Deterministic multi-signal outlier detection.

    Signals:
    - ratio to user median
    - ratio to category median
    - rarity in user history
    - non-recurring behavior
    - distribution tail (q95)
    """

    def detect(self, transactions: Sequence[AnalyticsTransaction]) -> Sequence[AnalyticsTransaction]:
        if not transactions:
            return tuple()

        amounts = [item.amount for item in transactions if item.amount > 0]
        if not amounts:
            return tuple(transactions)

        user_median = median(amounts)
        q95 = _quantile(amounts, 0.95)
        category_medians = _group_median_by_category(transactions)
        category_counts = _group_count_by_category(transactions)
        total_count = len(transactions)
        rarity_threshold = max(2, int(total_count * 0.05))

        result: List[AnalyticsTransaction] = []
        for item in transactions:
            ratio_to_user = (item.amount / user_median) if user_median > 0 else 0.0
            cat_median = category_medians.get(item.category_id)
            ratio_to_category = (
                (item.amount / cat_median)
                if cat_median is not None and cat_median > 0
                else 0.0
            )
            category_count = category_counts.get(item.category_id, 0)

            components: List[Tuple[str, float]] = []
            if ratio_to_user >= 3.0:
                components.append(("ratio_to_user_median", min(1.5, 0.5 + (ratio_to_user - 3.0) * 0.3)))
            if ratio_to_category >= 2.5:
                components.append(
                    ("ratio_to_category_median", min(1.2, 0.4 + (ratio_to_category - 2.5) * 0.25))
                )
            if category_count <= rarity_threshold and ratio_to_user >= 2.0:
                components.append(("rarity_in_history", 0.35))
            if not item.is_recurring and ratio_to_user >= 2.0:
                components.append(("non_recurring_behavior", 0.25))
            if item.amount >= q95 and ratio_to_user >= 2.0:
                components.append(("distribution_tail_q95", 0.35))

            score = sum(weight for _, weight in components)
            components.sort(key=lambda pair: pair[1], reverse=True)
            primary_source = components[0][0] if components else None
            is_large_one_time_purchase = (score >= 1.0) and (not item.is_recurring)

            result.append(
                AnalyticsTransaction(
                    transaction_id=item.transaction_id,
                    user_id=item.user_id,
                    category_id=item.category_id,
                    amount=item.amount,
                    is_recurring=item.is_recurring,
                    occurred_at=item.occurred_at,
                    is_large_one_time_purchase=is_large_one_time_purchase,
                    outlier_score=round(score, 4),
                    outlier_flag_source=primary_source,
                    metadata=dict(item.metadata),
                )
            )

        return tuple(result)


class BaselineMetricsBuilder:
    """Build full and baseline-adjusted metrics using robust statistics."""

    def build(self, transactions: Sequence[AnalyticsTransaction]) -> Mapping[str, float]:
        if not transactions:
            return {}

        full_amounts = [item.amount for item in transactions]
        adjusted_items = [
            item
            for item in transactions
            if not item.is_large_one_time_purchase
        ]
        adjusted_amounts = [item.amount for item in adjusted_items]

        recurring_full = sum(item.amount for item in transactions if item.is_recurring)
        recurring_adjusted = sum(item.amount for item in adjusted_items if item.is_recurring)
        full_total = sum(full_amounts)
        adjusted_total = sum(adjusted_amounts)
        full_count = len(full_amounts)

        avg_check = (full_total / full_count) if full_count > 0 else 0.0
        median_check = median(full_amounts) if full_amounts else 0.0
        trimmed_mean_check = _trimmed_mean(full_amounts, trim_ratio=0.1) if full_amounts else 0.0

        return {
            "total_expense_full": float(full_total),
            "total_expense_baseline_adjusted": float(adjusted_total),
            "recurring_amount_full": float(recurring_full),
            "recurring_amount_baseline_adjusted": float(recurring_adjusted),
            "tx_count": float(full_count),
            "avg_check": float(avg_check),
            "median_check": float(median_check),
            "trimmed_mean_check": float(trimmed_mean_check),
            "outlier_count": float(
                len([item for item in transactions if item.is_large_one_time_purchase])
            ),
        }


def _event_to_transaction(event: Mapping[str, object]) -> Optional[AnalyticsTransaction]:
    amount_raw = event.get("amount")
    if amount_raw is None:
        return None

    try:
        amount = float(amount_raw)
    except (TypeError, ValueError):
        return None

    category_id = event.get("category_id")
    if category_id is not None:
        try:
            category_id = int(category_id)
        except (TypeError, ValueError):
            category_id = None

    is_recurring = bool(event.get("is_recurring", False))
    return AnalyticsTransaction(
        transaction_id=(
            str(event.get("transaction_id"))
            if event.get("transaction_id") is not None
            else None
        ),
        user_id=(str(event.get("user_id")) if event.get("user_id") is not None else None),
        category_id=category_id,
        amount=amount,
        is_recurring=is_recurring,
        occurred_at=event.get("occurred_at"),
        metadata=dict(event),
    )


def _group_median_by_category(
    transactions: Sequence[AnalyticsTransaction],
) -> Mapping[Optional[int], float]:
    grouped: Dict[Optional[int], List[float]] = {}
    for item in transactions:
        grouped.setdefault(item.category_id, []).append(item.amount)

    medians: Dict[Optional[int], float] = {}
    for category_id, values in grouped.items():
        if not values:
            continue
        medians[category_id] = median(values)
    return medians


def _group_count_by_category(
    transactions: Sequence[AnalyticsTransaction],
) -> Mapping[Optional[int], int]:
    grouped: Dict[Optional[int], int] = {}
    for item in transactions:
        grouped[item.category_id] = grouped.get(item.category_id, 0) + 1
    return grouped


def _trimmed_mean(values: Sequence[float], trim_ratio: float) -> float:
    if not values:
        return 0.0
    if len(values) < 3:
        return sum(values) / len(values)

    sorted_values = sorted(values)
    trim_count = int(len(sorted_values) * trim_ratio)
    if trim_count <= 0:
        trimmed = sorted_values
    elif trim_count * 2 >= len(sorted_values):
        trimmed = sorted_values
    else:
        trimmed = sorted_values[trim_count:-trim_count]
    if not trimmed:
        return sum(sorted_values) / len(sorted_values)
    return sum(trimmed) / len(trimmed)


def _quantile(values: Sequence[float], quantile: float) -> float:
    if not values:
        return 0.0
    sorted_values = sorted(values)
    if len(sorted_values) == 1:
        return sorted_values[0]

    position = (len(sorted_values) - 1) * quantile
    lower = int(position)
    upper = min(lower + 1, len(sorted_values) - 1)
    if lower == upper:
        return sorted_values[lower]
    fraction = position - lower
    return sorted_values[lower] * (1 - fraction) + sorted_values[upper] * fraction
