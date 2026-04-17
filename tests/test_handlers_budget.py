"""
Тесты для handlers/budget.py
"""
import datetime
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

    inherited_budget = {
        "amount": 1000.0,
        "month": 3,
        "year": 2026,
    }
    current_budget = {
        "amount": 1000.0,
        "month": 4,
        "year": 2026,
        "notify_enabled": False,
        "notify_threshold": None,
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
    get_budget_mock.assert_called_once()
    inherited_mock.assert_called_once()
    set_budget_mock.assert_called_once()
    set_notif_mock.assert_called_once()
    check_now_mock.assert_called_once()
    mock_update.message.reply_text.assert_called()

    # Проверяем, что материализация делается на текущий месяц/год и с суммой inherited-бюджета
    _, call_kwargs = set_budget_mock.call_args
    if call_kwargs:
        assert call_kwargs["amount"] == 1000.0
    else:
        # set_budget(user_id, month, year, amount, project_id)
        args = set_budget_mock.call_args.args
        assert args[3] == 1000.0


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
    }

    with patch("handlers.budget.has_permission", new=AsyncMock(return_value=True)), \
         patch("handlers.budget.budgets_utils.get_budget", new=AsyncMock(return_value=None)), \
         patch("handlers.budget.budgets_utils.get_or_inherit_budget",
               new=AsyncMock(return_value=inherited_budget)):
        result = await budget_handler.edit_notification_start(mock_update, mock_context)

    assert result == budget_handler.EDITING_THRESHOLD
    sent_text = mock_update.message.reply_text.call_args.args[0]
    assert "унаследует бюджет" in sent_text
