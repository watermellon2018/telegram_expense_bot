"""
Тесты для utils/helpers.py
"""
import pytest
from unittest.mock import AsyncMock
from telegram.ext import ConversationHandler
from utils import helpers


def test_parse_add_command_with_slash():
    """Тест парсинга команды с /add"""
    result = helpers.parse_add_command("/add 100 продукты хлеб")
    
    assert result is not None
    assert result['amount'] == 100.0
    assert result['category'] == "продукты"
    assert result['description'] == "хлеб"


def test_parse_add_command_without_slash():
    """Тест парсинга команды без /add"""
    result = helpers.parse_add_command("200 транспорт такси")
    
    assert result is not None
    assert result['amount'] == 200.0
    assert result['category'] == "транспорт"
    assert result['description'] == "такси"


def test_parse_add_command_no_description():
    """Тест парсинга команды без описания"""
    result = helpers.parse_add_command("150 рестораны")
    
    assert result is not None
    assert result['amount'] == 150.0
    assert result['category'] == "рестораны"
    assert result['description'] == ""


def test_parse_add_command_invalid_format():
    """Тест парсинга невалидной команды"""
    result = helpers.parse_add_command("invalid command")
    
    assert result is None


def test_parse_add_command_invalid_amount():
    """Тест парсинга с невалидной суммой"""
    result = helpers.parse_add_command("abc продукты")
    
    assert result is None


@pytest.mark.asyncio
async def test_cancel_conversation_basic():
    """Тест базовой отмены conversation"""
    mock_update = AsyncMock()
    mock_context = AsyncMock()
    
    result = await helpers.cancel_conversation(
        mock_update,
        mock_context,
        "Отменено"
    )
    
    # Проверяем, что отправлено сообщение
    mock_update.message.reply_text.assert_called_once()
    
    # Проверяем возврат END
    assert result == ConversationHandler.END


@pytest.mark.asyncio
async def test_cancel_conversation_with_clear_data():
    """Тест отмены с очисткой данных"""
    from unittest.mock import MagicMock
    
    mock_update = AsyncMock()
    mock_context = AsyncMock()
    # Создаем MagicMock для user_data, чтобы можно было отследить вызовы clear()
    mock_user_data = MagicMock()
    mock_user_data.__getitem__ = MagicMock()
    mock_context.user_data = mock_user_data
    
    result = await helpers.cancel_conversation(
        mock_update,
        mock_context,
        "Отменено",
        clear_data=True
    )
    
    # Проверяем, что данные очищены
    mock_context.user_data.clear.assert_called_once()


@pytest.mark.asyncio
async def test_add_project_context_to_report_with_project():
    """Тест добавления контекста проекта к отчету"""
    from unittest.mock import patch
    
    report = "Тестовый отчет"
    user_id = 123456789
    project_id = 1
    
    mock_project = {'project_name': 'Тестовый проект'}
    
    # Патчим модуль projects внутри функции
    with patch('utils.projects.get_project_by_id', new=AsyncMock(return_value=mock_project)):
        result = await helpers.add_project_context_to_report(report, user_id, project_id)
        
        assert "Тестовый проект" in result
        assert report in result


@pytest.mark.asyncio
async def test_add_project_context_to_report_without_project():
    """Тест добавления контекста без проекта"""
    report = "Тестовый отчет"
    user_id = 123456789
    
    result = await helpers.add_project_context_to_report(report, user_id, None)
    
    assert "Общие расходы" in result
    assert report in result


def test_get_month_name():
    """Тест получения названия месяца"""
    assert helpers.get_month_name(1).lower() == "январь"
    assert helpers.get_month_name(6).lower() == "июнь"
    assert helpers.get_month_name(12).lower() == "декабрь"
