"""
Тесты для handlers/expense.py
"""
import pytest
from unittest.mock import patch, AsyncMock
from telegram.ext import ConversationHandler
from handlers.expense import (
    add_command, 
    handle_amount, 
    handle_category_callback, 
    handle_description,
    cancel,
    ENTERING_AMOUNT, 
    CHOOSING_CATEGORY
)
import config


@pytest.mark.asyncio
async def test_add_command(mock_update, mock_context):
    """Тест команды /add"""
    result = await add_command(mock_update, mock_context)
    
    # Проверяем, что запрашивается сумма
    mock_update.message.reply_text.assert_called_once()
    call_args = mock_update.message.reply_text.call_args[0][0]
    assert "сумму" in call_args.lower()
    
    # Проверяем, что возвращается правильное состояние
    assert result == ENTERING_AMOUNT


@pytest.mark.asyncio
async def test_handle_amount_valid(mock_update, mock_context):
    """Тест обработки валидной суммы"""
    mock_update.message.text = "100.50"
    
    # Mock категории для inline keyboard
    mock_categories = [
        {'category_id': 1, 'name': 'продукты', 'is_system': True, 'is_active': True, 'project_id': None},
        {'category_id': 2, 'name': 'транспорт', 'is_system': True, 'is_active': True, 'project_id': None},
    ]
    
    with patch('handlers.expense.categories.ensure_system_categories_exist', new=AsyncMock()) as mock_ensure, \
         patch('handlers.expense.categories.get_categories_for_user_project', new=AsyncMock(return_value=mock_categories)):
        
        result = await handle_amount(mock_update, mock_context)
        
        # Проверяем, что сумма сохранена
        assert mock_context.user_data['amount'] == 100.50
        
        # Проверяем, что запрашивается категория (inline keyboard)
        mock_update.message.reply_text.assert_called_once()
        
        # Проверяем переход к следующему состоянию
        assert result == CHOOSING_CATEGORY


@pytest.mark.asyncio
async def test_handle_amount_invalid(mock_update, mock_context):
    """Тест обработки невалидной суммы"""
    mock_update.message.text = "invalid"
    
    result = await handle_amount(mock_update, mock_context)
    
    # Проверяем, что выведено сообщение об ошибке
    mock_update.message.reply_text.assert_called_once()
    call_args = mock_update.message.reply_text.call_args[0][0]
    assert "ошибка" in call_args.lower() or "неверный" in call_args.lower()
    
    # Проверяем, что остаемся в том же состоянии
    assert result == ENTERING_AMOUNT


@pytest.mark.asyncio
async def test_handle_category_callback_valid(mock_update, mock_context):
    """Тест обработки валидной категории через callback"""
    from unittest.mock import MagicMock
    
    # Создаем mock для callback_query
    mock_update.callback_query = MagicMock()
    mock_update.callback_query.answer = AsyncMock()
    mock_update.callback_query.data = "cat_1"
    mock_update.callback_query.edit_message_text = AsyncMock()
    
    mock_context.user_data['amount'] = 100.0
    
    # Mock категории
    mock_category = {
        'category_id': 1,
        'name': 'продукты',
        'project_id': None,
        'is_system': True,
        'is_active': True
    }
    
    with patch('handlers.expense.categories.get_category_by_id', new=AsyncMock(return_value=mock_category)):
        result = await handle_category_callback(mock_update, mock_context)
        
        # Проверяем, что category_id сохранен
        assert mock_context.user_data['category_id'] == 1
        assert mock_context.user_data['category_name'] == 'продукты'
        
        # Проверяем, что callback был обработан
        mock_update.callback_query.answer.assert_called_once()


@pytest.mark.asyncio
async def test_handle_category_callback_invalid(mock_update, mock_context):
    """Тест обработки невалидной категории через callback"""
    from unittest.mock import MagicMock
    
    # Создаем mock для callback_query
    mock_update.callback_query = MagicMock()
    mock_update.callback_query.answer = AsyncMock()
    mock_update.callback_query.data = "cat_999"
    mock_update.callback_query.edit_message_text = AsyncMock()
    
    mock_context.user_data['amount'] = 100.0
    
    with patch('handlers.expense.categories.get_category_by_id', new=AsyncMock(return_value=None)):
        result = await handle_category_callback(mock_update, mock_context)
        
        # Проверяем, что выведено сообщение об ошибке
        mock_update.callback_query.edit_message_text.assert_called_once()
        call_args = mock_update.callback_query.edit_message_text.call_args[0][0]
        assert "не найдена" in call_args.lower() or "ошибка" in call_args.lower()


@pytest.mark.asyncio
async def test_handle_description_with_text(mock_update, mock_context):
    """Тест обработки описания с текстом"""
    mock_update.message.text = "покупка в магазине"
    mock_context.user_data.update({
        'amount': 100.0,
        'category_id': 1,
        'category_name': 'продукты'
    })
    
    with patch('handlers.expense.excel.add_expense', new=AsyncMock(return_value=True)):
        result = await handle_description(mock_update, mock_context)
        
        # Проверяем, что отправлено подтверждение
        mock_update.message.reply_text.assert_called()
        
        # Проверяем, что conversation завершен
        assert result == ConversationHandler.END


@pytest.mark.asyncio
async def test_cancel_command(mock_update, mock_context):
    """Тест отмены добавления расхода"""
    mock_context.user_data.update({
        'amount': 100.0,
        'category_id': 1,
        'category_name': 'продукты'
    })
    
    with patch('handlers.expense.helpers.cancel_conversation', new=AsyncMock(return_value=ConversationHandler.END)) as mock_cancel:
        result = await cancel(mock_update, mock_context)
        
        # Проверяем, что данные очищены
        assert 'amount' not in mock_context.user_data
        assert 'category_id' not in mock_context.user_data
        assert 'category_name' not in mock_context.user_data
        
        # Проверяем, что вызвана функция отмены
        mock_cancel.assert_called_once()
        
        assert result == ConversationHandler.END
