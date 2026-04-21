"""
Outlier handling / baseline adjustment layer.
"""

from abc import ABC, abstractmethod
from dataclasses import replace
from typing import Dict, Mapping, Optional, Tuple

from recommendation.models import AnalyticsSnapshot, BaselineAdjustment


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

    async def adjust(self, snapshot: AnalyticsSnapshot) -> AnalyticsSnapshot:
        if not self._metric_caps:
            return snapshot

        adjusted_metrics: Dict[str, float] = dict(snapshot.metrics)
        adjustments: Tuple[BaselineAdjustment, ...] = tuple(snapshot.adjustments)
        collected = []

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

        if not collected:
            return snapshot

        return replace(
            snapshot,
            metrics=adjusted_metrics,
            baseline_metrics=adjusted_metrics,
            adjustments=adjustments + tuple(collected),
        )

