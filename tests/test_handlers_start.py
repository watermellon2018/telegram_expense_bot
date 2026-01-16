"""
Тесты для handlers/start.py
"""
import pytest
from unittest.mock import patch, AsyncMock
from handlers.start import start, help_command, projects_menu, main_menu


@pytest.mark.asyncio
async def test_start_command(mock_update, mock_context):
    """Тест команды /start"""
    with patch('handlers.start.excel.create_user_dir') as mock_create_dir, \
         patch('handlers.start.projects.get_active_project', new=AsyncMock(return_value=None)):
        
        await start(mock_update, mock_context)
        
        # Проверяем, что создана директория пользователя
        mock_create_dir.assert_called_once_with(mock_update.effective_user.id)
        
        # Проверяем, что отправлено приветственное сообщение
        mock_update.message.reply_text.assert_called_once()
        
        # Проверяем, что инициализирован active_project_id
        assert 'active_project_id' in mock_context.user_data


@pytest.mark.asyncio
async def test_start_with_active_project(mock_update, mock_context):
    """Тест /start с активным проектом"""
    mock_project = {'project_id': 1, 'project_name': 'Test Project'}
    
    with patch('handlers.start.excel.create_user_dir'), \
         patch('handlers.start.projects.get_active_project', new=AsyncMock(return_value=mock_project)):
        
        await start(mock_update, mock_context)
        
        # Проверяем, что установлен активный проект
        assert mock_context.user_data['active_project_id'] == 1


@pytest.mark.asyncio
async def test_help_command(mock_update, mock_context):
    """Тест команды /help"""
    await help_command(mock_update, mock_context)
    
    # Проверяем, что отправлено сообщение с помощью
    mock_update.message.reply_text.assert_called_once()
    call_args = mock_update.message.reply_text.call_args[0][0]
    
    # Проверяем, что в сообщении есть список команд
    assert "/add" in call_args
    assert "/month" in call_args
    assert "/stats" in call_args


@pytest.mark.asyncio
async def test_projects_menu(mock_update, mock_context):
    """Тест меню проектов"""
    await projects_menu(mock_update, mock_context)
    
    # Проверяем, что отправлено сообщение
    mock_update.message.reply_text.assert_called_once()


@pytest.mark.asyncio
async def test_main_menu(mock_update, mock_context):
    """Тест главного меню"""
    await main_menu(mock_update, mock_context)
    
    # Проверяем, что отправлено сообщение с клавиатурой
    mock_update.message.reply_text.assert_called_once()
