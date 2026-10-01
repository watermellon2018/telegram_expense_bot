"""
Тесты UX выбора шаблона при создании проекта (handlers/project.py):
- ввод имени → показ клавиатуры шаблонов;
- создание обычного проекта (tpl_none) и тематического (tpl_vacation);
- команда /project_create остаётся «обычной» (без изоляции).
"""
from unittest.mock import AsyncMock, patch

import pytest
from telegram.ext import ConversationHandler

from handlers import project as project_handler


@pytest.mark.asyncio
async def test_create_name_step_shows_template_keyboard(mock_update, mock_context):
    """После ввода имени показывается клавиатура шаблонов, состояние CHOOSING_TEMPLATE."""
    mock_update.message.text = "Отпуск 2026"

    with patch("handlers.project.projects.get_project_by_name", new=AsyncMock(return_value=None)):
        state = await project_handler.button_project_create_name(mock_update, mock_context)

    assert state == project_handler.CHOOSING_TEMPLATE
    assert mock_context.user_data["new_project_name"] == "Отпуск 2026"

    kwargs = mock_update.message.reply_text.call_args.kwargs
    markup = kwargs["reply_markup"]
    callbacks = [btn.callback_data for row in markup.inline_keyboard for btn in row]
    assert "tpl_none" in callbacks
    assert "tpl_vacation" in callbacks
    assert "tpl_renovation" in callbacks


@pytest.mark.asyncio
async def test_create_name_step_rejects_duplicate(mock_update, mock_context):
    """Дубликат имени отклоняется на шаге ввода, выбор шаблона не показывается."""
    mock_update.message.text = "Существующий"

    with patch("handlers.project.projects.get_project_by_name",
               new=AsyncMock(return_value={"project_id": 9, "project_name": "Существующий"})):
        state = await project_handler.button_project_create_name(mock_update, mock_context)

    assert state == ConversationHandler.END
    assert "new_project_name" not in mock_context.user_data
    text = mock_update.message.reply_text.call_args.args[0]
    assert "уже существует" in text.lower()


@pytest.mark.asyncio
@pytest.mark.parametrize('template', [None, 'vacation'])
async def test_project_creation_collects_currency_before_writing(mock_update_with_callback, mock_context, template):
    u = mock_update_with_callback
    u.callback_query.data = 'tpl_' + (template or 'none')
    mock_context.user_data['new_project_name'] = 'Поездка'
    create = AsyncMock(return_value={'success': True, 'project_id': 50})
    with patch('handlers.project.projects.create_project', create), patch('handlers.project.projects.set_active_project', AsyncMock(return_value={'success': True})):
        assert await project_handler.button_project_create_template(u, mock_context) == project_handler.CHOOSING_REPORT_CURRENCY
        create.assert_not_called()
        u.callback_query.data = 'proj_report_USD'
        assert await project_handler.project_report_currency(u, mock_context) == project_handler.CHOOSING_INPUT_CURRENCY
        u.callback_query.data = 'proj_input_JPY'
        assert await project_handler.project_input_currency(u, mock_context) == project_handler.ENTERING_FALLBACK_RATE
        create.assert_not_called()
        assert await project_handler.finish_project_creation(u, mock_context, rate='0.006') == ConversationHandler.END
    create.assert_awaited_once_with(u.effective_user.id, 'Поездка', template, reporting_currency='USD', input_currency='JPY', fallback_rate='0.006')
    assert mock_context.user_data['active_project_id'] == 50


@pytest.mark.asyncio
async def test_expired_template_does_not_create(mock_update_with_callback, mock_context):
    mock_update_with_callback.callback_query.data = 'tpl_vacation'
    with patch('handlers.project.projects.create_project', AsyncMock()) as create:
        assert await project_handler.button_project_create_template(mock_update_with_callback, mock_context) == ConversationHandler.END
        create.assert_not_called()


@pytest.mark.asyncio
async def test_project_command_requests_reporting_currency(mock_update, mock_context):
    mock_update.message.text = '/project_create Командный'
    with patch('handlers.project.projects.create_project', AsyncMock()) as create:
        assert await project_handler.project_create_command(mock_update, mock_context) == project_handler.CHOOSING_REPORT_CURRENCY
        create.assert_not_called()
    assert mock_context.user_data['new_project_name'] == 'Командный'
    assert mock_context.user_data['new_project_template'] is None
