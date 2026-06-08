"""
Тесты для handlers/export.py
"""
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pandas as pd
import pytest

from handlers.export import (
    create_main_export_menu,
    create_month_selection_menu,
    create_year_selection_menu,
    export_stats_command,
    get_available_years,
    handle_export_callback,
    perform_export,
)


@pytest.mark.asyncio
async def test_export_command_no_args_shows_menu(mock_update, mock_context):
    """Тест /export без аргументов показывает меню"""
    mock_context.args = []

    await export_stats_command(mock_update, mock_context)

    # Проверяем, что отправлено сообщение с inline кнопками
    mock_update.message.reply_text.assert_called_once()
    call_args = mock_update.message.reply_text.call_args
    assert "reply_markup" in call_args[1]


@pytest.mark.asyncio
async def test_export_command_with_year(mock_update, mock_context):
    """Тест /export с указанием года - использует perform_export"""
    mock_context.args = ["2024"]
    mock_context.user_data = {}

    # Просто мокируем perform_export, чтобы проверить, что команда вызывает его правильно
    with patch('handlers.export.perform_export', new=AsyncMock()) as mock_perform:
        await export_stats_command(mock_update, mock_context)

        # Проверяем, что perform_export был вызван с правильными параметрами
        mock_perform.assert_called_once()
        call_args = mock_perform.call_args[0]
        assert call_args[0] == mock_update
        assert call_args[2] is None  # project_id
        assert call_args[3] == 2024  # year
        assert call_args[4] is None  # month


@pytest.mark.asyncio
async def test_export_command_no_data(mock_update, mock_context):
    """Тест /export когда нет данных"""
    mock_context.args = ["2024"]

    with patch('handlers.export.excel.get_all_expenses', new=AsyncMock(return_value=None)):
        await export_stats_command(mock_update, mock_context)

        # Проверяем, что отправлено сообщение об отсутствии данных
        mock_update.message.reply_text.assert_called_once()
        call_args = mock_update.message.reply_text.call_args[0][0]
        assert "нет данных" in call_args.lower()


@pytest.mark.asyncio
async def test_get_available_years(test_user_id):
    """Тест получения доступных годов"""
    mock_rows = [
        {'year': 2024},
        {'year': 2023},
        {'year': 2022}
    ]

    with patch('handlers.export.db.fetch', new=AsyncMock(return_value=mock_rows)):
        years = await get_available_years(test_user_id)

        assert years == [2024, 2023, 2022]


@pytest.mark.asyncio
async def test_get_available_years_no_data(test_user_id):
    """Тест получения годов когда нет данных"""
    with patch('handlers.export.db.fetch', new=AsyncMock(return_value=[])):
        years = await get_available_years(test_user_id)

        assert years == []


def test_create_main_export_menu():
    """Тест создания главного меню экспорта"""
    menu = create_main_export_menu()

    # Проверяем, что меню содержит кнопки
    assert len(menu.inline_keyboard) == 3
    assert menu.inline_keyboard[0][0].text == "📊 Экспорт всех расходов"
    assert menu.inline_keyboard[1][0].text == "📅 Экспорт за год"
    assert menu.inline_keyboard[2][0].text == "📆 Экспорт за месяц"


def test_create_year_selection_menu():
    """Тест создания меню выбора года"""
    years = [2024, 2023, 2022, 2021]
    menu = create_year_selection_menu(years)

    # Проверяем, что есть кнопки для всех годов
    assert len(menu.inline_keyboard) > 0
    # Последняя кнопка должна быть "Назад"
    assert menu.inline_keyboard[-1][0].text == "⬅️ Назад"


def test_create_month_selection_menu():
    """Тест создания меню выбора месяца"""
    menu = create_month_selection_menu(2024)

    # Проверяем, что есть 12 месяцев + кнопка "Назад"
    assert len(menu.inline_keyboard) == 5  # 4 ряда по 3 месяца + кнопка "Назад"
    # Последняя кнопка должна быть "Назад"
    assert menu.inline_keyboard[-1][0].text == "⬅️ Назад"


@pytest.mark.asyncio
async def test_handle_export_callback_main_menu(mock_update_with_callback, mock_context):
    """Тест callback для главного меню"""
    mock_update_with_callback.callback_query.data = "export:main"

    await handle_export_callback(mock_update_with_callback, mock_context)

    # Проверяем, что отредактировано сообщение
    mock_update_with_callback.callback_query.edit_message_text.assert_called_once()


@pytest.mark.asyncio
async def test_handle_export_callback_year_select(mock_update_with_callback, mock_context):
    """Тест callback для выбора года"""
    mock_update_with_callback.callback_query.data = "export:year:select"

    with patch('handlers.export.get_available_years', new=AsyncMock(return_value=[2024, 2023])):
        await handle_export_callback(mock_update_with_callback, mock_context)

        # Проверяем, что показано меню выбора года
        mock_update_with_callback.callback_query.edit_message_text.assert_called_once()


@pytest.mark.asyncio
async def test_perform_export_message_selection():
    """Тест что perform_export правильно выбирает message объект для callback query"""
    # Этот тест проверяет логику выбора message (из callback_query или из update.message)
    # без запуска всей функции экспорта

    # Создаем mock update с callback_query
    mock_callback_update = Mock()
    mock_callback_update.callback_query = Mock()
    mock_callback_update.callback_query.message = AsyncMock()
    mock_callback_update.message = None

    # Создаем mock update без callback_query
    mock_direct_update = Mock()
    mock_direct_update.callback_query = None
    mock_direct_update.message = AsyncMock()

    mock_df = pd.DataFrame({'date': [], 'amount': [], 'category': [], 'month': []})

    with patch('handlers.export.excel.get_all_expenses', new=AsyncMock(return_value=mock_df)):
        # Тест 1: callback query update - должен использовать callback_query.message
        await perform_export(mock_callback_update, 123, None, None, None)
        mock_callback_update.callback_query.message.reply_text.assert_called()

        # Тест 2: direct message update - должен использовать update.message
        await perform_export(mock_direct_update, 123, None, None, None)
        mock_direct_update.message.reply_text.assert_called()
