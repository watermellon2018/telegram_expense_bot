"""
Регрессионные тесты на формат пользовательских сообщений.
"""
import pytest
from unittest.mock import AsyncMock, patch

from handlers.start import start
from handlers.project import project_info_command
from utils import helpers


@pytest.mark.asyncio
async def test_start_message_keeps_core_format_blocks(mock_update, mock_context):
    """Стартовое сообщение должно содержать ключевые секции с примерами."""
    with patch("handlers.start.excel.create_user_dir"), \
         patch("handlers.start.projects.get_active_project", new=AsyncMock(return_value=None)):
        await start(mock_update, mock_context)

    text = mock_update.message.reply_text.call_args.args[0]
    assert "Я бот для учета и анализа расходов" in text
    assert "/add <сумма> <категория> [описание]" in text
    assert "Например: /add 100 продукты хлеб и молоко" in text
    assert "Для получения справки используйте команду /help" in text


@pytest.mark.asyncio
async def test_project_info_message_format_for_active_project(mock_update, mock_context):
    """Формат /project_info в активном проекте должен содержать ключевые поля."""
    project = {
        "project_id": 42,
        "project_name": "Trip",
        "created_date": "2026-04-19",
        "role": "owner",
    }
    stats = {"count": 3, "total": 150.0}
    members = [{"user_id": "1"}, {"user_id": "2"}]

    with patch("handlers.project.projects.get_active_project", new=AsyncMock(return_value=project)), \
         patch("handlers.project.projects.get_project_stats", new=AsyncMock(return_value=stats)), \
         patch("handlers.project.projects.get_project_members", new=AsyncMock(return_value=members)), \
         patch("utils.permissions.get_role_description", return_value="👑 Владелец"):
        await project_info_command(mock_update, mock_context)

    text = mock_update.message.reply_text.call_args.args[0]
    assert "📁 Текущий проект: Trip" in text
    assert "ID: 42" in text
    assert "Создан: 2026-04-19" in text
    assert "Расходов: 3" in text
    assert "Общая сумма: 150.00" in text
    assert "Участников: 2" in text


def test_format_month_expenses_regression_contains_expected_sections():
    """Месячный отчёт должен сохранять порядок секций и русские заголовки."""
    report = helpers.format_month_expenses(
        {
            "total": 150.0,
            "count": 2,
            "by_participant": {"ID: 1": 120.0, "ID: 2": 30.0},
            "by_category": {"продукты": 100.0, "транспорт": 50.0},
        },
        month=4,
        year=2026,
    )

    assert "📊 Статистика расходов за Апрель 2026 года:" in report
    assert "💰 Общая сумма: 150.00" in report
    assert "🧾 Количество транзакций: 2" in report
    assert "👥 По участникам:" in report
    assert "📋 Расходы по категориям:" in report
    assert report.index("👥 По участникам:") < report.index("📋 Расходы по категориям:")
