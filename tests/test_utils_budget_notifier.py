"""
Тесты для utils/budget_notifier.py
"""
import datetime
from unittest.mock import AsyncMock, patch

import pytest

from utils import budget_notifier


def test_should_send_only_first_time():
    """Уведомление отправляется только если ранее не отправляли."""
    assert budget_notifier._should_send(None, 100.0, 120.0) is True
    assert budget_notifier._should_send(datetime.datetime.now(), 100.0, 120.0) is False


@pytest.mark.asyncio
async def test_process_budget_does_not_resend_overspent_when_already_notified():
    """Если перерасход уже был уведомлён, повторная отправка не выполняется."""
    bot = AsyncMock()
    budget = {
        "id": 1,
        "user_id": "123",
        "project_id": None,
        "amount": 1000.0,
        "notify_threshold": None,
        "overspent_notified_at": datetime.datetime.now(),
        "threshold_notified_at": None,
        "last_notified_spending": 1100.0,
    }

    with patch("utils.budget_notifier.excel.get_month_expenses", new=AsyncMock(return_value={"total": 1200.0})), \
         patch("utils.budget_notifier._send_to_users", new=AsyncMock()) as send_mock, \
         patch("utils.budget_notifier.budgets_utils.update_notification_state", new=AsyncMock()) as update_mock:
        await budget_notifier._process_budget(
            bot=bot,
            budget=budget,
            month=4,
            year=2026,
            now=datetime.datetime.now(),
        )

    send_mock.assert_not_called()
    update_mock.assert_not_called()


@pytest.mark.asyncio
async def test_process_budget_sends_overspent_once_and_updates_state():
    """При первом пересечении лимита отправляет уведомление и обновляет состояние."""
    bot = AsyncMock()
    now = datetime.datetime(2026, 4, 17, 12, 0, 0)
    budget = {
        "id": 2,
        "user_id": "123",
        "project_id": None,
        "amount": 1000.0,
        "notify_threshold": None,
        "overspent_notified_at": None,
        "threshold_notified_at": None,
        "last_notified_spending": None,
    }

    with patch("utils.budget_notifier.excel.get_month_expenses", new=AsyncMock(return_value={"total": 1200.0})), \
         patch("utils.budget_notifier._send_to_users", new=AsyncMock()) as send_mock, \
         patch("utils.budget_notifier.budgets_utils.update_notification_state", new=AsyncMock()) as update_mock:
        await budget_notifier._process_budget(
            bot=bot,
            budget=budget,
            month=4,
            year=2026,
            now=now,
        )

    send_mock.assert_called_once()
    update_mock.assert_called_once_with(
        budget_id=2,
        threshold_notified_at=None,
        overspent_notified_at=now,
        last_notified_spending=1200.0,
    )


@pytest.mark.asyncio
async def test_check_budget_notifications_uses_local_now_for_month_year():
    """
    Проверяем, что выбор месяца/года идёт от локального now() (без timezone-aware UTC now()).
    """
    local_now = datetime.datetime(2026, 1, 31, 23, 30, 0)

    with patch("utils.budget_notifier.datetime.datetime") as dt_mock, \
         patch("utils.budget_notifier.budgets_utils.get_all_active_budgets_with_notifications",
               new=AsyncMock(return_value=[])) as active_mock:
        dt_mock.now.return_value = local_now
        await budget_notifier.check_budget_notifications(bot=AsyncMock())

    active_mock.assert_called_once_with(1, 2026)
