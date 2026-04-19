"""
Тесты project-режима handlers/stats.py для графиков по участникам.
"""
import pytest
from unittest.mock import AsyncMock, mock_open, patch

from handlers.stats import month_command, stats_command


@pytest.mark.asyncio
async def test_month_command_sends_participant_chart_in_project_mode(mock_update, mock_context):
    """В project-режиме /month должен отправлять график распределения по участникам."""
    mock_context.user_data["active_project_id"] = 42

    with patch("handlers.stats.excel.get_month_expenses", new=AsyncMock(return_value={
        "total": 100.0,
        "by_category": {"продукты": 100.0},
        "by_participant": {"ID: 1": 100.0},
        "count": 1,
    })), \
         patch("handlers.stats.incomes.get_month_incomes", new=AsyncMock(return_value={"total": 0.0, "count": 0, "by_category": {}})), \
         patch("utils.budgets.get_or_inherit_budget", new=AsyncMock(return_value=None)), \
         patch("handlers.stats.helpers.format_month_expenses", return_value="report"), \
         patch("handlers.stats.helpers.add_project_context_to_report", new=AsyncMock(side_effect=lambda r, *_: r)), \
         patch("handlers.stats.visualization.create_monthly_pie_chart", new=AsyncMock(return_value=None)), \
         patch("handlers.stats.visualization.create_monthly_participant_distribution_chart", new=AsyncMock(return_value="participants.png")), \
         patch("handlers.stats.os.path.exists", return_value=True), \
         patch("builtins.open", mock_open(read_data=b"img")):
        await month_command(mock_update, mock_context)

    assert mock_update.message.reply_photo.call_count == 1
    assert mock_update.message.reply_photo.call_args.kwargs["caption"] == "Распределение расходов по участникам"


@pytest.mark.asyncio
async def test_month_command_skips_participant_chart_when_no_data(mock_update, mock_context):
    """Если participant chart не создан, /month не должен отправлять фото по участникам."""
    mock_context.user_data["active_project_id"] = 42

    with patch("handlers.stats.excel.get_month_expenses", new=AsyncMock(return_value={
        "total": 100.0,
        "by_category": {"продукты": 100.0},
        "by_participant": {"ID: 1": 100.0},
        "count": 1,
    })), \
         patch("handlers.stats.incomes.get_month_incomes", new=AsyncMock(return_value={"total": 0.0, "count": 0, "by_category": {}})), \
         patch("utils.budgets.get_or_inherit_budget", new=AsyncMock(return_value=None)), \
         patch("handlers.stats.helpers.format_month_expenses", return_value="report"), \
         patch("handlers.stats.helpers.add_project_context_to_report", new=AsyncMock(side_effect=lambda r, *_: r)), \
         patch("handlers.stats.visualization.create_monthly_pie_chart", new=AsyncMock(return_value=None)), \
         patch("handlers.stats.visualization.create_monthly_participant_distribution_chart", new=AsyncMock(return_value=None)):
        await month_command(mock_update, mock_context)

    mock_update.message.reply_photo.assert_not_called()


@pytest.mark.asyncio
async def test_stats_command_passes_project_id_to_category_chart(mock_update, mock_context):
    """В project-режиме /stats должен строить category chart с project_id."""
    mock_context.user_data["active_project_id"] = 42

    with patch("handlers.stats.visualization.create_category_distribution_chart", new=AsyncMock(return_value=None)) as category_chart_mock, \
         patch("handlers.stats.visualization.create_budget_comparison_chart", new=AsyncMock(return_value=None)), \
         patch("handlers.stats.visualization.create_income_distribution_chart", new=AsyncMock(return_value=None)), \
         patch("handlers.stats.visualization.create_income_vs_expense_chart", new=AsyncMock(return_value=None)), \
         patch("handlers.stats.visualization.create_project_participant_distribution_chart", new=AsyncMock(return_value=None)):
        await stats_command(mock_update, mock_context)

    category_chart_mock.assert_awaited_once()
    assert category_chart_mock.await_args.kwargs.get("project_id") == 42


@pytest.mark.asyncio
async def test_stats_command_calls_participant_chart_only_in_project_mode(mock_update, mock_context):
    """Годовой participant chart должен вызываться только когда активен проект."""
    mock_context.user_data["active_project_id"] = None

    with patch("handlers.stats.visualization.create_category_distribution_chart", new=AsyncMock(return_value=None)), \
         patch("handlers.stats.visualization.create_budget_comparison_chart", new=AsyncMock(return_value=None)), \
         patch("handlers.stats.visualization.create_income_distribution_chart", new=AsyncMock(return_value=None)), \
         patch("handlers.stats.visualization.create_income_vs_expense_chart", new=AsyncMock(return_value=None)), \
         patch("handlers.stats.visualization.create_project_participant_distribution_chart", new=AsyncMock(return_value=None)) as participant_chart_mock:
        await stats_command(mock_update, mock_context)

    participant_chart_mock.assert_not_awaited()

