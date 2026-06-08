from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest

from recommendation.models import MonthlyCategorySummary, MonthlyUserSummary
from recommendation.repositories.monthly_summaries import PostgresMonthlySummaryRepository


@pytest.mark.asyncio
async def test_upsert_and_get_monthly_user_summary():
    repository = PostgresMonthlySummaryRepository()
    now = datetime.utcnow()
    row = {
        "id": 1,
        "user_id": "u-sum-1",
        "month_key": "2026-04",
        "total_expense_full": 10000.0,
        "total_income_full": 15000.0,
        "net_balance_full": 5000.0,
        "tx_count": 120,
        "avg_check": 83.33,
        "median_check": 45.0,
        "recurring_amount_full": 3200.0,
        "recurring_share_full": 0.32,
        "small_expense_amount_full": 900.0,
        "small_expense_share_full": 0.09,
        "total_expense_baseline_adjusted": 8200.0,
        "recurring_amount_baseline_adjusted": 2800.0,
        "created_at": now,
        "updated_at": now,
    }

    summary = MonthlyUserSummary(
        id=None,
        user_id="u-sum-1",
        month_key="2026-04",
        total_expense_full=10000.0,
        total_income_full=15000.0,
        net_balance_full=5000.0,
        tx_count=120,
        avg_check=83.33,
        median_check=45.0,
        recurring_amount_full=3200.0,
        recurring_share_full=0.32,
        small_expense_amount_full=900.0,
        small_expense_share_full=0.09,
        total_expense_baseline_adjusted=8200.0,
        recurring_amount_baseline_adjusted=2800.0,
    )

    with patch(
        "recommendation.repositories.monthly_summaries.db.fetchrow",
        new=AsyncMock(side_effect=[row, row]),
    ):
        saved = await repository.upsert_monthly_user_summary(summary)
        loaded = await repository.get_monthly_user_summary("u-sum-1", "2026-04")

    assert saved.id == 1
    assert loaded is not None
    assert loaded.total_expense_baseline_adjusted == 8200.0
    assert loaded.recurring_amount_baseline_adjusted == 2800.0


@pytest.mark.asyncio
async def test_upsert_and_get_monthly_category_summaries():
    repository = PostgresMonthlySummaryRepository()
    now = datetime.utcnow()
    row_food = {
        "id": 10,
        "user_id": "u-sum-2",
        "month_key": "2026-04",
        "category_id": 1,
        "total_amount_full": 2500.0,
        "total_amount_baseline_adjusted": 2100.0,
        "tx_count": 30,
        "share_in_month": 0.25,
        "created_at": now,
        "updated_at": now,
    }
    row_transport = {
        "id": 11,
        "user_id": "u-sum-2",
        "month_key": "2026-04",
        "category_id": 2,
        "total_amount_full": 900.0,
        "total_amount_baseline_adjusted": 900.0,
        "tx_count": 18,
        "share_in_month": 0.09,
        "created_at": now,
        "updated_at": now,
    }
    input_rows = [
        MonthlyCategorySummary(
            id=None,
            user_id="u-sum-2",
            month_key="2026-04",
            category_id=1,
            total_amount_full=2500.0,
            total_amount_baseline_adjusted=2100.0,
            tx_count=30,
            share_in_month=0.25,
        ),
        MonthlyCategorySummary(
            id=None,
            user_id="u-sum-2",
            month_key="2026-04",
            category_id=2,
            total_amount_full=900.0,
            total_amount_baseline_adjusted=900.0,
            tx_count=18,
            share_in_month=0.09,
        ),
    ]

    with patch(
        "recommendation.repositories.monthly_summaries.db.fetchrow",
        new=AsyncMock(side_effect=[row_food, row_transport]),
    ), patch(
        "recommendation.repositories.monthly_summaries.db.fetch",
        new=AsyncMock(return_value=[row_food, row_transport]),
    ):
        saved = await repository.upsert_monthly_category_summaries(input_rows)
        loaded = await repository.get_monthly_category_summaries("u-sum-2", "2026-04")

    assert len(saved) == 2
    assert len(loaded) == 2
    assert loaded[0].category_id == 1
    assert loaded[0].total_amount_baseline_adjusted == 2100.0

