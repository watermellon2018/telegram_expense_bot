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
async def test_create_template_none_creates_plain_project(mock_update_with_callback, mock_context):
    """tpl_none → create_project с template_key=None, проект активируется."""
    mock_update_with_callback.callback_query.data = "tpl_none"
    mock_context.user_data["new_project_name"] = "Поездка"

    create_mock = AsyncMock(return_value={
        "success": True, "project_id": 50, "project_name": "Поездка",
        "categories_isolated": False, "template_key": None, "message": "Проект 'Поездка' создан",
    })
    with patch("handlers.project.projects.create_project", new=create_mock), \
         patch("handlers.project.projects.set_active_project", new=AsyncMock()):
        state = await project_handler.button_project_create_template(mock_update_with_callback, mock_context)

    assert state == ConversationHandler.END
    create_mock.assert_awaited_once()
    # template_key передан как None (третий позиционный аргумент)
    assert create_mock.call_args.args[2] is None
    assert mock_context.user_data["active_project_id"] == 50


@pytest.mark.asyncio
async def test_create_template_vacation_creates_isolated_project(mock_update_with_callback, mock_context):
    """tpl_vacation → create_project с template_key='vacation', в ответе упомянута изоляция."""
    mock_update_with_callback.callback_query.data = "tpl_vacation"
    mock_context.user_data["new_project_name"] = "Отпуск"

    create_mock = AsyncMock(return_value={
        "success": True, "project_id": 60, "project_name": "Отпуск",
        "categories_isolated": True, "template_key": "vacation", "message": "Проект 'Отпуск' создан",
    })
    with patch("handlers.project.projects.create_project", new=create_mock), \
         patch("handlers.project.projects.set_active_project", new=AsyncMock()):
        state = await project_handler.button_project_create_template(mock_update_with_callback, mock_context)

    assert state == ConversationHandler.END
    assert create_mock.call_args.args[2] == "vacation"
    body = mock_update_with_callback.callback_query.edit_message_text.call_args.args[0]
    assert "перелёт" in body  # перечислены категории шаблона
    assert "общие категории" in body.lower()  # упомянуто, что глобальные не показываются


@pytest.mark.asyncio
async def test_create_template_expired_session(mock_update_with_callback, mock_context):
    """Если имя потерялось из user_data — сообщение об истёкшей сессии, проект не создаётся."""
    mock_update_with_callback.callback_query.data = "tpl_vacation"
    # new_project_name отсутствует

    create_mock = AsyncMock()
    with patch("handlers.project.projects.create_project", new=create_mock):
        state = await project_handler.button_project_create_template(mock_update_with_callback, mock_context)

    assert state == ConversationHandler.END
    create_mock.assert_not_called()


@pytest.mark.asyncio
async def test_project_create_command_stays_plain(mock_update, mock_context):
    """Команда /project_create создаёт обычный проект (без template_key)."""
    mock_update.message.text = "/project_create Командный"

    create_mock = AsyncMock(return_value={
        "success": True, "project_id": 70, "project_name": "Командный",
        "categories_isolated": False, "message": "Проект 'Командный' создан",
    })
    with patch("handlers.project.projects.create_project", new=create_mock), \
         patch("handlers.project.projects.set_active_project", new=AsyncMock()):
        await project_handler.project_create_command(mock_update, mock_context)

    create_mock.assert_awaited_once()
    # вызвана позиционно с (user_id, name) — без template_key
    assert len(create_mock.call_args.args) == 2
    assert create_mock.call_args.args[1] == "Командный"
