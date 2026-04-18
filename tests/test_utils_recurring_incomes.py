"""Тесты для utils/recurring_incomes.py"""

import datetime
import pytest
from unittest.mock import AsyncMock, patch

from utils import recurring_incomes


@pytest.mark.asyncio
async def test_create_rule_creates_initial_income_for_today():
    """При старте правила сегодня должен создаваться фактический доход."""
    with patch("utils.recurring_incomes.db.fetchval", new=AsyncMock(return_value=55)), \
         patch("utils.recurring_incomes.db.execute", new=AsyncMock()) as mock_execute:
        rule_id = await recurring_incomes.create_rule(
            user_id="1",
            amount=1000,
            income_category_id=2,
            comment="Зарплата",
            project_id=None,
            frequency_type="monthly",
            interval_value=None,
            weekday=None,
            day_of_month=None,
            is_last_day_of_month=False,
            start_date=datetime.date.today(),
        )

    assert rule_id == 55
    assert mock_execute.call_count >= 1


@pytest.mark.asyncio
async def test_process_recurring_incomes_idempotent_same_day():
    """Воркер не должен дублировать income за один и тот же день по одному правилу."""
    now_rule = {
        "id": 77,
        "user_id": "1",
        "amount": 500,
        "income_category_id": 2,
        "category_name": "Зарплата",
        "comment": "Зарплата",
        "project_id": None,
        "frequency_type": "monthly",
        "interval_value": None,
        "weekday": None,
        "day_of_month": None,
        "is_last_day_of_month": False,
    }

    # first fetch: due rules, then idempotency check returns already existing marker
    with patch("utils.recurring_incomes.db.fetch", new=AsyncMock(return_value=[now_rule])), \
         patch("utils.recurring_incomes.db.fetchval", new=AsyncMock(return_value=1)), \
         patch("utils.recurring_incomes.db.execute", new=AsyncMock()) as mock_execute:

        class Bot:
            async def send_message(self, *args, **kwargs):
                return None

        await recurring_incomes.process_recurring_incomes(Bot())

    # При already_created не должно быть вставки новой записи
    assert mock_execute.call_count == 0
