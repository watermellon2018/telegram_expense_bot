"""Тесты /month с учетом доходов."""

import pytest
from unittest.mock import AsyncMock, patch

from handlers.stats import month_command


@pytest.mark.asyncio
async def test_month_command_includes_income_and_net(mock_update, mock_context):
    """Отчет /month должен содержать сумму доходов и чистый результат."""
    mock_context.user_data["active_project_id"] = None

    with patch("handlers.stats.excel.get_month_expenses", new=AsyncMock(return_value={
        "total": 1200.0,
        "by_category": {"продукты": 1200.0},
        "count": 3,
    })), \
         patch("handlers.stats.incomes.get_month_incomes", new=AsyncMock(return_value={
             "total": 3000.0,
             "by_category": {"зарплата": 3000.0},
             "count": 1,
         })), \
         patch("handlers.stats.visualization.create_monthly_pie_chart", new=AsyncMock(return_value=None)), \
         patch("handlers.stats.helpers.format_month_expenses", return_value="expense-part"), \
         patch("utils.budgets.get_or_inherit_budget", new=AsyncMock(return_value=None)):
        await month_command(mock_update, mock_context)

    assert mock_update.message.reply_text.called
    text = mock_update.message.reply_text.call_args[0][0]
    assert "expense-part" in text
    assert "3000.00" in text
    assert "1800.00" in text


@pytest.mark.asyncio
async def test_month_command_counts_only_factual_income_records(mock_update, mock_context):
    """В /month должна учитываться только сумма фактических income записей."""
    mock_context.user_data["active_project_id"] = None

    with patch("handlers.stats.excel.get_month_expenses", new=AsyncMock(return_value={
        "total": 500.0,
        "by_category": {},
        "count": 1,
    })), \
         patch("handlers.stats.incomes.get_month_incomes", new=AsyncMock(return_value={
             # Имитируем, что сервис уже вернул только фактические записи
             "total": 700.0,
             "by_category": {"бизнес": 700.0},
             "count": 2,
         })), \
         patch("handlers.stats.visualization.create_monthly_pie_chart", new=AsyncMock(return_value=None)), \
         patch("handlers.stats.helpers.format_month_expenses", return_value="expense-part"), \
         patch("utils.budgets.get_or_inherit_budget", new=AsyncMock(return_value=None)):
        await month_command(mock_update, mock_context)

    text = mock_update.message.reply_text.call_args[0][0]
    assert "700.00" in text
    assert "200.00" in text
