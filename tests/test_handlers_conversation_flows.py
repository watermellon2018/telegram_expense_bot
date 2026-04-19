"""
Тесты conversation-flow для project/expense хендлеров.
"""
import pytest
from unittest.mock import AsyncMock, patch
from telegram.ext import ConversationHandler

from handlers import project as project_handler
from handlers import expense as expense_handler


@pytest.mark.asyncio
async def test_project_delete_choose_callback_cancel_finishes_flow(mock_update_with_callback, mock_context):
    """Нажатие cancel в выборе проекта завершает удаление."""
    mock_update_with_callback.callback_query.data = "del_proj_cancel"

    result = await project_handler.project_delete_choose_callback(mock_update_with_callback, mock_context)

    assert result == ConversationHandler.END
    mock_update_with_callback.callback_query.edit_message_text.assert_called_once_with(
        "Удаление проекта отменено."
    )


@pytest.mark.asyncio
async def test_project_delete_choose_callback_valid_moves_to_confirmation(mock_update_with_callback, mock_context):
    """После выбора проекта обработчик должен перейти в CONFIRMING_DELETE."""
    mock_update_with_callback.callback_query.data = "del_proj_42"
    mock_project = {"project_id": 42, "project_name": "Trip"}

    with patch("handlers.project.projects.get_project_by_id", new=AsyncMock(return_value=mock_project)), \
         patch("handlers.project.projects.get_project_stats", new=AsyncMock(return_value={"count": 5, "total": 123.45})):
        result = await project_handler.project_delete_choose_callback(mock_update_with_callback, mock_context)

    assert result == project_handler.CONFIRMING_DELETE
    assert mock_context.user_data["delete_project_id"] == 42
    assert mock_context.user_data["delete_project_name"] == "Trip"
    assert mock_update_with_callback.callback_query.edit_message_text.called


@pytest.mark.asyncio
async def test_project_delete_confirm_cancel_clears_context_and_ends(mock_update_with_callback, mock_context):
    """Cancel на финальном шаге должен очищать контекст и завершать диалог."""
    mock_update_with_callback.callback_query.data = "del_proj_cancel"
    mock_context.user_data["delete_project_id"] = 42
    mock_context.user_data["delete_project_name"] = "Trip"

    result = await project_handler.project_delete_confirm(mock_update_with_callback, mock_context)

    assert result == ConversationHandler.END
    assert "delete_project_id" not in mock_context.user_data
    assert "delete_project_name" not in mock_context.user_data


@pytest.mark.asyncio
async def test_expense_add_command_no_permission_ends_conversation(mock_update, mock_context):
    """При отсутствии прав /add должен завершаться без перехода в ввод суммы."""
    mock_update.message.text = "/add"

    with patch("handlers.expense.helpers.get_active_project_id", new=AsyncMock(return_value=42)), \
         patch("utils.permissions.has_permission", new=AsyncMock(return_value=False)):
        result = await expense_handler.add_command(mock_update, mock_context)

    assert result == ConversationHandler.END
    sent_text = mock_update.message.reply_text.call_args.args[0]
    assert "нет прав" in sent_text.lower()


@pytest.mark.asyncio
async def test_expense_category_create_branch_switches_state(mock_update_with_callback, mock_context):
    """Ветвь cat_create должна переводить диалог в CREATING_CATEGORY."""
    mock_update_with_callback.callback_query.data = "cat_create"

    result = await expense_handler.handle_category_callback(mock_update_with_callback, mock_context)

    assert result == expense_handler.CREATING_CATEGORY
    mock_update_with_callback.callback_query.edit_message_text.assert_called_once()
