"""
Тесты для handlers/budget.py
"""
import datetime
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest
from telegram.ext import ConversationHandler

from handlers import budget as budget_handler


@pytest.mark.asyncio
async def test_cancel_edit_notification_returns_end(mock_update, mock_context):
    result = await budget_handler._cancel_edit_notification(mock_update, mock_context)
    assert result == ConversationHandler.END
    mock_update.message.reply_text.assert_called_once()


@pytest.mark.asyncio
async def test_back_to_main_menu_from_edit_notification_returns_end(mock_update, mock_context):
    with patch("handlers.budget.get_main_menu_keyboard", return_value="MAIN_KB"):
        result = await budget_handler._back_to_main_menu_from_edit_notification(
            mock_update, mock_context
        )

    assert result == ConversationHandler.END
    mock_update.message.reply_text.assert_called_once_with(
        "Главное меню",
        reply_markup="MAIN_KB",
    )


@pytest.mark.asyncio
async def test_edit_notification_threshold_materializes_inherited_budget(mock_update, mock_context):
    """
    Если бюджет на текущий месяц отсутствует, но есть унаследованный,
    обработчик должен создать запись текущего месяца и сохранить порог.
    """
    mock_update.message.text = "900"
    mock_update.effective_user.id = 123456789
    mock_context.user_data["active_project_id"] = None
    mock_context.user_data["budget_project_id"] = None
    mock_context.user_data["budget_currency"] = "JPY"

    inherited_budget = {
        "amount": 1000.0,
        "month": 3,
        "year": 2026,
        "currency": "JPY",
    }
    current_budget = {
        "amount": 1000.0,
        "month": 4,
        "year": 2026,
        "notify_enabled": False,
        "notify_threshold": None,
        "currency": "JPY",
    }

    with patch("handlers.budget.budgets_utils.get_budget", new=AsyncMock(return_value=None)) as get_budget_mock, \
         patch("handlers.budget.budgets_utils.get_or_inherit_budget",
               new=AsyncMock(return_value=inherited_budget)) as inherited_mock, \
         patch("handlers.budget.budgets_utils.set_budget",
               new=AsyncMock(return_value=current_budget)) as set_budget_mock, \
         patch("handlers.budget.budgets_utils.set_notification",
               new=AsyncMock(return_value={**current_budget, "notify_enabled": True, "notify_threshold": 900.0})) as set_notif_mock, \
         patch("handlers.budget.check_user_budget_now", new=AsyncMock()) as check_now_mock:
        result = await budget_handler.edit_notification_threshold(mock_update, mock_context)

    assert result == ConversationHandler.END
    now = datetime.datetime.now()
    get_budget_mock.assert_awaited_once_with(123456789, now.month, now.year, None)
    inherited_mock.assert_awaited_once_with(123456789, now.month, now.year, None)
    set_budget_mock.assert_awaited_once_with(123456789, now.month, now.year, 1000.0, None, currency="JPY")
    set_notif_mock.assert_awaited_once_with(123456789, now.month, now.year, Decimal("900"), None)
    check_now_mock.assert_awaited_once_with(mock_context.bot, 123456789, None)
    mock_update.message.reply_text.assert_called()

    assert "900 JPY" in mock_update.message.reply_text.call_args.args[0]


@pytest.mark.asyncio
async def test_edit_notification_start_shows_inherited_note(mock_update, mock_context):
    """
    При отсутствии бюджета за текущий месяц, но наличии унаследованного,
    пользователю показывается пояснение об унаследованном бюджете.
    """
    mock_update.effective_user.id = 123456789
    mock_context.user_data["active_project_id"] = None

    inherited_budget = {
        "amount": 1500.0,
        "month": 2,
        "year": 2026,
        "notify_threshold": None,
        "currency": "JPY",
    }

    with patch("handlers.budget.has_permission", new=AsyncMock(return_value=True)), \
         patch("handlers.budget.currencies.get_reporting_currency", new=AsyncMock(return_value="JPY")), \
         patch("handlers.budget.budgets_utils.get_budget", new=AsyncMock(return_value=None)), \
         patch("handlers.budget.budgets_utils.get_or_inherit_budget",
               new=AsyncMock(return_value=inherited_budget)):
        result = await budget_handler.edit_notification_start(mock_update, mock_context)

    assert result == budget_handler.EDITING_THRESHOLD
    sent_text = mock_update.message.reply_text.call_args.args[0]
    assert "унаследует бюджет" in sent_text
    assert "1 500 JPY" in sent_text
    assert mock_context.user_data["budget_currency"] == "JPY"


@pytest.mark.asyncio
async def test_edit_threshold_does_not_materialize_legacy_budget(mock_update, mock_context):
    mock_update.message.text = "900"
    mock_context.user_data.update(budget_project_id=42, budget_currency="JPY")
    old_budget = {"amount": Decimal("1000"), "month": 3, "year": 2026, "currency": None}
    with patch("handlers.budget.budgets_utils.get_budget", new=AsyncMock(return_value=None)), \
         patch("handlers.budget.budgets_utils.get_or_inherit_budget", new=AsyncMock(return_value=old_budget)), \
         patch("handlers.budget.budgets_utils.set_budget", new=AsyncMock()) as set_budget, \
         patch("handlers.budget.budgets_utils.set_notification", new=AsyncMock()) as set_notification:
        result = await budget_handler.edit_notification_threshold(mock_update, mock_context)
    assert result == ConversationHandler.END
    set_budget.assert_not_awaited()
    set_notification.assert_not_awaited()
    assert "не найден" in mock_update.message.reply_text.call_args.args[0]


@pytest.mark.asyncio
@pytest.mark.parametrize("initial_project", [None, 42])
async def test_budget_dialog_preserves_context_after_active_project_switch(mock_update, mock_context, initial_project):
    mock_context.user_data["active_project_id"] = initial_project
    currency = AsyncMock(return_value="JPY")
    with patch("handlers.budget.has_permission", new=AsyncMock(return_value=True)), \
         patch("handlers.budget.currencies.get_reporting_currency", new=currency), \
         patch("handlers.budget.budgets_utils.get_budget", new=AsyncMock(return_value=None)), \
         patch("handlers.budget.budgets_utils.set_budget", new=AsyncMock(return_value={"currency": "JPY"})) as save, \
         patch("handlers.budget.budgets_utils.disable_notification", new=AsyncMock()) as disable:
        assert await budget_handler.set_budget_start(mock_update, mock_context) == budget_handler.ENTERING_AMOUNT
        mock_context.user_data["active_project_id"] = 99
        mock_update.message.text = "1500"
        assert await budget_handler.set_budget_amount(mock_update, mock_context) == budget_handler.ASKING_NOTIFY
        mock_update.message.text = "Нет"
        assert await budget_handler.set_budget_notify_choice(mock_update, mock_context) == ConversationHandler.END

    now = datetime.datetime.now()
    user_id = mock_update.effective_user.id
    currency.assert_awaited_once_with(user_id, initial_project)
    save.assert_awaited_once_with(user_id, now.month, now.year, Decimal("1500"), initial_project, currency="JPY")
    disable.assert_awaited_once_with(user_id, now.month, now.year, initial_project)
