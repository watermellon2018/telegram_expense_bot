"""
Тесты обработки ошибок внешних зависимостей в хендлерах.
"""
import pytest
from unittest.mock import AsyncMock, patch

from handlers.start import start
from handlers.stats import month_command, stats_command
from handlers.report import report_command


@pytest.mark.asyncio
async def test_start_handles_storage_error(mock_update, mock_context):
    """Ошибка create_user_dir не должна падать наружу, бот отправляет fallback-текст."""
    with patch("handlers.start.excel.create_user_dir", side_effect=RuntimeError("disk error")):
        await start(mock_update, mock_context)

    sent_text = mock_update.message.reply_text.call_args.args[0]
    assert "произошла ошибка при запуске бота" in sent_text.lower()


@pytest.mark.asyncio
async def test_month_command_handles_dependency_error(mock_update, mock_context):
    """Ошибка в источнике данных /month должна приводить к user-friendly сообщению."""
    with patch("handlers.stats.excel.get_month_expenses", new=AsyncMock(side_effect=RuntimeError("db down"))), \
         patch("handlers.stats.incomes.get_month_incomes", new=AsyncMock(return_value={"total": 0.0})), \
         patch("utils.budgets.get_or_inherit_budget", new=AsyncMock(return_value=None)):
        await month_command(mock_update, mock_context)

    sent_text = mock_update.message.reply_text.call_args.args[0]
    assert "ошибка при получении статистики" in sent_text.lower()


@pytest.mark.asyncio
async def test_stats_command_handles_chart_error(mock_update, mock_context):
    """Падение генерации графиков в /stats должно обрабатываться без traceback пользователю."""
    with patch("handlers.stats.visualization.create_category_distribution_chart", new=AsyncMock(side_effect=RuntimeError("matplotlib error"))), \
         patch("handlers.stats.visualization.create_budget_comparison_chart", new=AsyncMock(return_value=None)), \
         patch("handlers.stats.visualization.create_income_distribution_chart", new=AsyncMock(return_value=None)), \
         patch("handlers.stats.visualization.create_income_vs_expense_chart", new=AsyncMock(return_value=None)):
        await stats_command(mock_update, mock_context)

    sent_text = mock_update.message.reply_text.call_args.args[0]
    assert "ошибка при построении графиков" in sent_text.lower()


@pytest.mark.asyncio
async def test_report_command_handles_generator_error(mock_update, mock_context):
    """Если PDF-генератор падает, report handler отправляет сообщение об ошибке."""
    wait_msg = AsyncMock()
    mock_update.message.reply_text = AsyncMock(return_value=wait_msg)

    with patch("handlers.report.report_generator.generate_pdf_report", new=AsyncMock(side_effect=RuntimeError("wkhtmltopdf failed"))):
        await report_command(mock_update, mock_context)

    # Первый вызов reply_text — wait message, второй — сообщение об ошибке
    assert mock_update.message.reply_text.await_count == 2
    error_text = mock_update.message.reply_text.await_args_list[1].args[0]
    assert "ошибка при генерации отчёта" in error_text.lower()

