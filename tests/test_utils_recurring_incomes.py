"""Тесты для utils/recurring_incomes.py"""

import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = pytest.mark.usefixtures("mock_currency_context")

from utils import recurring_incomes


@pytest.mark.asyncio
async def test_create_rule_creates_initial_income_for_today():
    """При старте правила сегодня должен создаваться фактический доход."""
    conn = MagicMock()
    conn.fetchval = AsyncMock(return_value=55)
    conn.execute = AsyncMock()
    conn.transaction.return_value.__aenter__ = AsyncMock(return_value=conn)
    conn.transaction.return_value.__aexit__ = AsyncMock(return_value=False)
    acquire = MagicMock()
    acquire.__aenter__ = AsyncMock(return_value=conn)
    acquire.__aexit__ = AsyncMock(return_value=False)
    mock_execute = conn.execute
    with patch("utils.recurring_incomes.db.transaction", return_value=acquire):
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
            # create_rule сравнивает start_date с utcnow().date(); используем UTC,
            # чтобы тест не зависел от смещения локальной даты относительно UTC.
            start_date=datetime.datetime.utcnow().date(),
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
        "status": "active",
        "next_run_at": datetime.datetime.utcnow() - datetime.timedelta(days=1),
    }

    conn = MagicMock()
    conn.fetchrow = AsyncMock(return_value=now_rule)
    conn.fetchval = AsyncMock(return_value=1)
    conn.execute = AsyncMock()
    conn.transaction.return_value.__aenter__ = AsyncMock(return_value=conn)
    conn.transaction.return_value.__aexit__ = AsyncMock(return_value=False)
    acquire = MagicMock()
    acquire.__aenter__ = AsyncMock(return_value=conn)
    acquire.__aexit__ = AsyncMock(return_value=False)
    bot = AsyncMock()

    # A due rule is refreshed under its row lock; today's operation already exists.
    with patch("utils.recurring_incomes.db.fetch", new=AsyncMock(return_value=[now_rule])), \
         patch("utils.recurring_incomes.db.transaction", return_value=acquire):
        await recurring_incomes.process_recurring_incomes(bot)

    conn.fetchrow.assert_awaited_once()
    assert "FOR UPDATE" in conn.fetchrow.await_args.args[0]
    assert conn.fetchrow.await_args.args[1] == 77
    conn.fetchval.assert_awaited_once()
    assert "SELECT 1 FROM incomes" in conn.fetchval.await_args.args[0]
    # The already generated day advances the schedule, with no second INSERT or notification.
    conn.execute.assert_awaited_once()
    assert "UPDATE recurring_incomes SET next_run_at" in conn.execute.await_args.args[0]
    assert conn.execute.await_args.args[1] > datetime.datetime.utcnow()
    assert conn.execute.await_args.args[2] == 77
    conn.transaction.return_value.__aexit__.assert_awaited_once_with(None, None, None)
    bot.send_message.assert_not_awaited()
