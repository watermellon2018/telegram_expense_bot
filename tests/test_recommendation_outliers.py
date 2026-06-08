from datetime import datetime

import pytest

from recommendation.models import AnalyticsSnapshot
from recommendation.outliers import (
    BaselineMetricsBuilder,
    BaselineOutlierHandler,
    OutlierDetectionService,
    _event_to_transaction,
)


@pytest.mark.asyncio
async def test_large_one_time_purchase_is_detected_and_adjusted():
    events = [
        {"transaction_id": f"t{i}", "amount": 100.0, "category_id": 1, "is_recurring": False}
        for i in range(1, 13)
    ]
    events.append(
        {
            "transaction_id": "t-big",
            "amount": 5000.0,
            "category_id": 1,
            "is_recurring": False,
        }
    )

    snapshot = AnalyticsSnapshot(
        user_id="u-out-1",
        project_id=None,
        generated_at=datetime.utcnow(),
        events=tuple(events),
    )

    handler = BaselineOutlierHandler()
    adjusted = await handler.adjust(snapshot)

    assert adjusted.metrics["outlier_count"] == 1.0
    assert adjusted.metrics["total_expense_full"] > adjusted.metrics["total_expense_baseline_adjusted"]
    assert adjusted.metadata["outlier_events"][-1]["is_large_one_time_purchase"] is True


def test_baseline_builder_uses_median_and_trimmed_mean_stably():
    detector = OutlierDetectionService()
    builder = BaselineMetricsBuilder()

    events = [
        {"transaction_id": f"n{i}", "amount": amount, "category_id": 2, "is_recurring": False}
        for i, amount in enumerate([95, 98, 100, 102, 101, 99, 97, 103, 96, 104], start=1)
    ]
    events.append(
        {
            "transaction_id": "n-outlier",
            "amount": 10000.0,
            "category_id": 2,
            "is_recurring": False,
        }
    )

    transactions = []
    for event in events:
        transactions.append(_event_to_transaction(event))
    transactions = [item for item in transactions if item is not None]

    flagged = detector.detect(transactions)
    metrics = builder.build(flagged)

    assert metrics["outlier_count"] == 1.0
    assert metrics["median_check"] < metrics["avg_check"]
    assert abs(metrics["median_check"] - 100.0) < 5.0
    assert metrics["trimmed_mean_check"] < metrics["avg_check"]
    assert metrics["total_expense_full"] > metrics["total_expense_baseline_adjusted"]
