"""User-visible currency flows, with database and Telegram boundaries mocked."""

from decimal import Decimal
from unittest.mock import AsyncMock, call

import pytest
from telegram.ext import ConversationHandler

from handlers import currency as currency_handler
from handlers import expense
from utils import currencies, expense_creation, permissions, projects


def snapshot(code, amount="1500"):
    return {"amount": Decimal(amount), "currency": code, "reporting_amount": Decimal("10.00"),
            "reporting_currency": "USD", "fx_source": "cbr"}


@pytest.mark.asyncio
@pytest.mark.parametrize("selected_code", ["JPY", "KRW"])
async def test_add_buttons_preserve_source_currency_and_project(
    mock_update, mock_update_with_callback, mock_context, monkeypatch, selected_code,
):
    uid = mock_update.effective_user.id
    mock_update.message.text = "/add"
    mock_context.user_data["active_project_id"] = 42
    mock_context.bot_data = {}
    monkeypatch.setattr(permissions, "has_permission", AsyncMock(return_value=True))
    monkeypatch.setattr(currencies, "get_input_currency", AsyncMock(return_value="JPY"))
    monkeypatch.setattr(currencies, "get_reporting_currency", AsyncMock(return_value="USD"))
    set_default = AsyncMock()
    monkeypatch.setattr(currencies, "set_input_currency", set_default)
    category = {"category_id": 7, "name": "еда"}
    categories = AsyncMock(return_value=[category])
    monkeypatch.setattr(expense.categories, "get_categories_for_user_project", categories)
    monkeypatch.setattr(expense.categories, "ensure_system_categories_exist", AsyncMock())
    create = AsyncMock(return_value={"status": "created", "expense_id": 99, "money": snapshot(selected_code)})
    monkeypatch.setattr(expense_creation, "process_new_expense", create)
    monkeypatch.setattr(expense, "check_user_budget_now", AsyncMock())
    monkeypatch.setattr(projects, "get_project_by_id", AsyncMock(return_value={"project_name": "Поездка"}))

    assert await expense.add_command(mock_update, mock_context) == expense.CHOOSING_CURRENCY
    buttons = [button for row in mock_update.message.reply_text.call_args.kwargs["reply_markup"].inline_keyboard for button in row]
    assert any(button.callback_data == "exp_cur_JPY" and "✓" in button.text for button in buttons)
    assert {button.callback_data for button in buttons} == {"exp_cur_JPY", "exp_cur_USD", "exp_cur_other"}
    assert mock_context.user_data["expense_project_id"] == 42
    assert mock_context.user_data["expense_currency"] == "JPY"

    # The user switches active project while this expense dialog is still open.
    mock_context.user_data["active_project_id"] = 99
    query = mock_update_with_callback.callback_query
    if selected_code == "KRW":
        query.data = "exp_cur_other"
        assert await expense.handle_currency_callback(mock_update_with_callback, mock_context) == expense.CHOOSING_CURRENCY
        all_buttons = query.edit_message_text.call_args.kwargs["reply_markup"].inline_keyboard
        assert any(button.callback_data == "exp_cur_KRW" for row in all_buttons for button in row)
    query.data = f"exp_cur_{selected_code}"
    assert await expense.handle_currency_callback(mock_update_with_callback, mock_context) == expense.ENTERING_AMOUNT
    mock_update.message.text = "1500"
    assert await expense.handle_amount(mock_update, mock_context) == expense.CHOOSING_CATEGORY
    query.data = "cat_7"
    assert await expense.handle_category_callback(mock_update_with_callback, mock_context) == expense.ENTERING_DESCRIPTION
    mock_update.message.text = "/skip"
    assert await expense.handle_description(mock_update, mock_context) == ConversationHandler.END

    assert categories.await_args_list == [call(uid, 42), call(uid, 42)]
    create.assert_awaited_once_with(
        mock_context.bot, author_id=uid, amount=Decimal("1500"), category_id=7, category_name="еда",
        description="", project_id=42, bot_data=mock_context.bot_data, currency=selected_code,
    )
    set_default.assert_not_awaited()
    assert f"1 500 {selected_code} ≈ 10.00 USD" in mock_update.message.reply_text.call_args.args[0]
    assert "expense_project_id" not in mock_context.user_data
    assert "expense_currency" not in mock_context.user_data


@pytest.mark.asyncio
@pytest.mark.parametrize("step", ["currency", "description"])
async def test_missing_expense_context_is_rejected(
    mock_update, mock_update_with_callback, mock_context, monkeypatch, step,
):
    mock_context.user_data.update(active_project_id=99, amount=Decimal("1500"), category_id=7,
                                  category_name="еда", expense_currency="JPY")
    create = AsyncMock()
    monkeypatch.setattr(expense_creation, "process_new_expense", create)
    if step == "currency":
        mock_update_with_callback.callback_query.data = "exp_cur_KRW"
        result = await expense.handle_currency_callback(mock_update_with_callback, mock_context)
        text = mock_update_with_callback.callback_query.edit_message_text.call_args.args[0]
    else:
        mock_update.message.text = "/skip"
        result = await expense.handle_description(mock_update, mock_context)
        text = mock_update.message.reply_text.call_args.args[0]
    assert result == ConversationHandler.END
    assert "/add" in text
    create.assert_not_awaited()


@pytest.mark.asyncio
async def test_quick_text_forwards_explicit_krw(mock_update, mock_context, monkeypatch):
    mock_context.user_data["active_project_id"] = 42
    mock_context.bot_data = {}
    mock_update.message.text = "1500 KRW еда обед"
    uid = mock_update.effective_user.id
    monkeypatch.setattr(permissions, "has_permission", AsyncMock(return_value=True))
    category = AsyncMock(return_value={"category_id": 7, "name": "еда"})
    monkeypatch.setattr(expense.categories, "get_category_by_name", category)
    create = AsyncMock(return_value={"status": "created", "expense_id": 99, "money": snapshot("KRW")})
    monkeypatch.setattr(expense_creation, "process_new_expense", create)
    monkeypatch.setattr(projects, "get_project_by_id", AsyncMock(return_value={"project_name": "Корея"}))
    monkeypatch.setattr(expense, "check_user_budget_now", AsyncMock())
    await expense.text_handler(mock_update, mock_context)
    category.assert_awaited_once_with(uid, "еда", 42)
    create.assert_awaited_once_with(
        mock_context.bot, author_id=uid, amount=Decimal("1500"), category_id=7, category_name="еда",
        description="обед", project_id=42, bot_data=mock_context.bot_data, currency="KRW",
    )
    assert "1 500 KRW ≈ 10.00 USD" in mock_update.message.reply_text.call_args.args[0]
    assert mock_context.user_data["recent_currencies"]["42"] == ["KRW"]


@pytest.mark.asyncio
async def test_input_currency_settings_are_personal_and_keep_selected_project(
    mock_update_with_callback, mock_context, monkeypatch,
):
    uid = mock_update_with_callback.effective_user.id
    mock_context.user_data.update(currency_project_id=42, currency_action="input", active_project_id=99)
    mock_update_with_callback.callback_query.data = "cur_code_KRW"
    set_input = AsyncMock()
    set_reporting = AsyncMock()
    monkeypatch.setattr(currencies, "set_input_currency", set_input)
    monkeypatch.setattr(currencies, "set_reporting_currency", set_reporting)
    monkeypatch.setattr(currencies, "get_reporting_currency", AsyncMock(return_value="USD"))
    monkeypatch.setattr(currencies, "get_input_currency", AsyncMock(return_value="KRW"))
    monkeypatch.setattr(projects, "get_project_by_id", AsyncMock(return_value={"project_name": "Корея", "role": "editor"}))
    assert await currency_handler.currency_selected(mock_update_with_callback, mock_context) == currency_handler.MENU
    set_input.assert_awaited_once_with(uid, 42, "KRW")
    set_reporting.assert_not_awaited()
    text = mock_update_with_callback.callback_query.edit_message_text.call_args.args[0]
    assert "Ваша валюта ввода: KRW" in text
    assert "Валюта отчётности: USD" in text


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["owner", "editor"])
async def test_reporting_settings_buttons_require_owner(mock_update, mock_context, monkeypatch, role):
    mock_context.user_data["active_project_id"] = 42
    monkeypatch.setattr(currencies, "get_reporting_currency", AsyncMock(return_value="USD"))
    monkeypatch.setattr(currencies, "get_input_currency", AsyncMock(return_value="KRW"))
    monkeypatch.setattr(projects, "get_project_by_id", AsyncMock(return_value={"project_name": "Корея", "role": role}))
    assert await currency_handler.currency_command(mock_update, mock_context) == currency_handler.MENU
    keyboard = mock_update.message.reply_text.call_args.kwargs["reply_markup"].inline_keyboard
    actions = {button.callback_data for row in keyboard for button in row}
    expected = {"cur_input", "cur_cancel"}
    if role == "owner":
        expected |= {"cur_report", "cur_fallback"}
    assert actions == expected


@pytest.mark.asyncio
async def test_nonowner_cannot_open_forged_reporting_action(mock_update_with_callback, mock_context, monkeypatch):
    mock_context.user_data.update(currency_project_id=42, currency_can_manage=False)
    mock_update_with_callback.callback_query.data = "cur_report"
    save = AsyncMock()
    monkeypatch.setattr(currencies, "set_reporting_currency", save)
    assert await currency_handler.currency_action(mock_update_with_callback, mock_context) == ConversationHandler.END
    save.assert_not_awaited()
    assert "currency_action" not in mock_context.user_data
    assert "владельцу" in mock_update_with_callback.callback_query.edit_message_text.call_args.args[0]


@pytest.mark.asyncio
async def test_reporting_selection_handles_owner_access_revoked(mock_update_with_callback, mock_context, monkeypatch):
    mock_context.user_data.update(currency_project_id=42, currency_can_manage=True, currency_action="report")
    mock_update_with_callback.callback_query.data = "cur_code_KRW"
    save = AsyncMock(side_effect=PermissionError("Нет прав на изменение проекта"))
    monkeypatch.setattr(currencies, "set_reporting_currency", save)
    assert await currency_handler.currency_selected(mock_update_with_callback, mock_context) == ConversationHandler.END
    save.assert_awaited_once_with(mock_update_with_callback.effective_user.id, 42, "KRW")
    text = mock_update_with_callback.callback_query.edit_message_text.call_args.args[0]
    assert "Нет прав" in text and "/currency" in text
