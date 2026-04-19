"""
Тесты прав доступа и ролевого поведения в handlers/project_management.py
"""
import pytest
from unittest.mock import AsyncMock, patch

from handlers import project_management as pm


@pytest.mark.asyncio
async def test_show_members_list_permission_denied(mock_update_with_callback, mock_context):
    """Без VIEW_MEMBERS обработчик должен вернуть сообщение об отказе."""
    mock_update_with_callback.callback_query.data = "proj_members_42"

    with patch("handlers.project_management.has_permission", new=AsyncMock(return_value=False)):
        await pm.show_members_list(mock_update_with_callback, mock_context)

    mock_update_with_callback.callback_query.edit_message_text.assert_called_once_with(
        "❌ У вас нет прав на просмотр участников."
    )


@pytest.mark.asyncio
async def test_show_invite_dialog_permission_denied(mock_update_with_callback, mock_context):
    """Без INVITE_MEMBERS приглашение должно быть запрещено."""
    mock_update_with_callback.callback_query.data = "proj_invite_42"

    with patch("handlers.project_management.has_permission", new=AsyncMock(return_value=False)):
        await pm.show_invite_dialog(mock_update_with_callback, mock_context)

    mock_update_with_callback.callback_query.edit_message_text.assert_called_once_with(
        "❌ Только владелец может приглашать участников."
    )


@pytest.mark.asyncio
async def test_show_role_management_permission_denied(mock_update_with_callback, mock_context):
    """Без CHANGE_ROLES управление ролями должно быть запрещено."""
    mock_update_with_callback.callback_query.data = "proj_roles_42"

    with patch("handlers.project_management.has_permission", new=AsyncMock(return_value=False)):
        await pm.show_role_management(mock_update_with_callback, mock_context)

    mock_update_with_callback.callback_query.edit_message_text.assert_called_once_with(
        "❌ Только владелец может изменять роли."
    )


@pytest.mark.asyncio
async def test_project_settings_menu_for_owner_shows_owner_actions(mock_update, mock_context):
    """У владельца должны быть кнопки приглашения и управления ролями."""
    mock_context.user_data["active_project_id"] = 42
    project = {"project_name": "Trip", "role": "owner", "is_owner": True}

    with patch("handlers.project_management.projects.get_project_by_id", new=AsyncMock(return_value=project)), \
         patch("handlers.project_management.projects.get_project_stats", new=AsyncMock(return_value={"count": 1, "total": 100.0})), \
         patch("handlers.project_management.projects.get_project_members", new=AsyncMock(return_value=[{"user_id": "1"}])), \
         patch("handlers.project_management.get_role_description", return_value="👑 Владелец"):
        await pm.project_settings_menu(mock_update, mock_context)

    kwargs = mock_update.message.reply_text.call_args.kwargs
    markup = kwargs["reply_markup"]
    callbacks = [btn.callback_data for row in markup.inline_keyboard for btn in row]

    assert "proj_members_42" in callbacks
    assert "proj_invite_42" in callbacks
    assert "proj_roles_42" in callbacks
    assert "proj_leave_42" not in callbacks


@pytest.mark.asyncio
async def test_project_settings_menu_for_viewer_shows_leave_only(mock_update, mock_context):
    """У не-владельца должна быть кнопка выхода и не должно быть owner-кнопок."""
    mock_context.user_data["active_project_id"] = 42
    project = {"project_name": "Trip", "role": "viewer", "is_owner": False}

    with patch("handlers.project_management.projects.get_project_by_id", new=AsyncMock(return_value=project)), \
         patch("handlers.project_management.projects.get_project_stats", new=AsyncMock(return_value={"count": 1, "total": 100.0})), \
         patch("handlers.project_management.projects.get_project_members", new=AsyncMock(return_value=[{"user_id": "1"}])), \
         patch("handlers.project_management.get_role_description", return_value="👁️ Наблюдатель"):
        await pm.project_settings_menu(mock_update, mock_context)

    kwargs = mock_update.message.reply_text.call_args.kwargs
    markup = kwargs["reply_markup"]
    callbacks = [btn.callback_data for row in markup.inline_keyboard for btn in row]

    assert "proj_members_42" in callbacks
    assert "proj_leave_42" in callbacks
    assert "proj_invite_42" not in callbacks
    assert "proj_roles_42" not in callbacks

