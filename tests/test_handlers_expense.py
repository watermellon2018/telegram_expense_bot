"""
Тесты для handlers/expense.py
"""
import pytest
from unittest.mock import patch, AsyncMock
from telegram.ext import ConversationHandler
from handlers.expense import (
    add_command, 
    handle_amount, 
    handle_category, 
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
    
    result = await handle_amount(mock_update, mock_context)
    
    # Проверяем, что сумма сохранена
    assert mock_context.user_data['amount'] == 100.50
    
    # Проверяем, что запрашивается категория
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
async def test_handle_category_valid(mock_update, mock_context):
    """Тест обработки валидной категории"""
    mock_update.message.text = "продукты"
    mock_context.user_data['amount'] = 100.0
    
    result = await handle_category(mock_update, mock_context)
    
    # Проверяем, что категория сохранена
    assert mock_context.user_data['category'] == "продукты"
    
    # Проверяем отправку сообщения
    mock_update.message.reply_text.assert_called_once()


@pytest.mark.asyncio
async def test_handle_category_invalid(mock_update, mock_context):
    """Тест обработки невалидной категории"""
    mock_update.message.text = "несуществующая_категория"
    mock_context.user_data['amount'] = 100.0
    
    result = await handle_category(mock_update, mock_context)
    
    # Проверяем, что выведено сообщение об ошибке
    mock_update.message.reply_text.assert_called_once()
    call_args = mock_update.message.reply_text.call_args[0][0]
    assert "недоступн" in call_args.lower() or "неверн" in call_args.lower() or "не найдена" in call_args.lower()


@pytest.mark.asyncio
async def test_handle_description_with_text(mock_update, mock_context):
    """Тест обработки описания с текстом"""
    mock_update.message.text = "покупка в магазине"
    mock_context.user_data.update({
        'amount': 100.0,
        'category': 'продукты'
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
        'category': 'продукты'
    })
    
    with patch('handlers.expense.helpers.cancel_conversation', new=AsyncMock(return_value=ConversationHandler.END)) as mock_cancel:
        result = await cancel(mock_update, mock_context)
        
        # Проверяем, что данные очищены
        assert 'amount' not in mock_context.user_data
        assert 'category' not in mock_context.user_data
        
        # Проверяем, что вызвана функция отмены
        mock_cancel.assert_called_once()
        
        assert result == ConversationHandler.END
