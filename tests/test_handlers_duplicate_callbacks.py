"""
Тесты callback-обработчиков сценария дубликатов и уведомлений (feature_110).

Покрывают обязательные сценарии ТЗ:
 14. Исключённый участник не может использовать старый callback.
 15. Один пользователь не может повторно отметить тот же расход как дубликат.
 16. Пользователь без прав не может удалить расход.
 18. Удалённый или недоступный расход корректно обрабатывается при старом callback.
А также: защита callback подтверждения от чужого пользователя и двойного нажатия.
"""

import datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import config
from handlers import duplicate as dup
from handlers import expense_notifications as en
from utils import expense_creation


def _make_update(user_id, callback_data):
    """Собирает mock Update с callback_query."""
    query = AsyncMock()
    query.data = callback_data
    query.answer = AsyncMock()
    query.edit_message_text = AsyncMock()
    query.message = AsyncMock()
    query.message.reply_text = AsyncMock()
    update = MagicMock()
    update.callback_query = query
    update.effective_user = MagicMock()
    update.effective_user.id = user_id
    return update, query


def _make_context(bot_data=None):
    ctx = MagicMock()
    ctx.bot = AsyncMock()
    ctx.bot_data = bot_data if bot_data is not None else {}
    ctx.user_data = {}
    return ctx


# ---------------------------------------------------------------------------
# Подтверждение дубликата: защита от чужого пользователя и устаревшего черновика
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_confirm_rejected_for_other_user():
    """Сценарий 14 (вариант): чужой пользователь не может подтвердить чужой черновик."""
    bot_data = {}
    draft = {"author_id": "111", "amount": 100, "category_id": 5,
             "category_name": "кафе", "description": "", "project_id": 1}
    draft_id = expense_creation._store_draft(bot_data, owner_user_id=111, draft=draft)

    # Подтверждает другой пользователь (222)
    update, query = _make_update(222, f"dupconfirm_{draft_id}")
    ctx = _make_context(bot_data)

    with patch("handlers.duplicate.expense_creation.confirm_pending_expense",
               new=AsyncMock()) as confirm_mock:
        await dup.dup_confirm_callback(update, ctx)

    # Не должно быть попытки создания
    confirm_mock.assert_not_called()
    query.answer.assert_awaited()
    # alert про доступ только автору
    args, kwargs = query.answer.call_args
    assert kwargs.get("show_alert") is True


@pytest.mark.asyncio
async def test_confirm_expired_draft():
    """Истёкший черновик → сообщение об устаревании, расход не создаётся."""
    update, query = _make_update(111, "dupconfirm_deadbeef")
    ctx = _make_context({})
    with patch("handlers.duplicate.expense_creation.confirm_pending_expense",
               new=AsyncMock()) as confirm_mock:
        await dup.dup_confirm_callback(update, ctx)
    confirm_mock.assert_not_called()
    query.answer.assert_awaited()


@pytest.mark.asyncio
async def test_confirm_double_press_results_already():
    """Сценарий 8: двойное нажатие — второй раз статус already, не создаётся дубль."""
    bot_data = {}
    draft = {"author_id": "111", "amount": 100, "category_id": 5,
             "category_name": "кафе", "description": "", "project_id": 1}
    draft_id = expense_creation._store_draft(bot_data, owner_user_id=111, draft=draft)
    update, query = _make_update(111, f"dupconfirm_{draft_id}")
    ctx = _make_context(bot_data)

    with patch("handlers.duplicate.expense_creation.confirm_pending_expense",
               new=AsyncMock(return_value={"status": "already", "expense_id": 5})):
        await dup.dup_confirm_callback(update, ctx)

    query.edit_message_text.assert_awaited()
    text = query.edit_message_text.call_args.args[0]
    assert "уже добавлен" in text.lower()


# ---------------------------------------------------------------------------
# Просмотр найденного расхода: сценарий 18 (расход удалён)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_view_handles_deleted_expense():
    """Сценарий 18: найденный расход удалён до нажатия 'Посмотреть'."""
    bot_data = {}
    draft = {"author_id": "111", "amount": 100, "category_id": 5,
             "category_name": "кафе", "description": "", "project_id": 1}
    draft_id = expense_creation._store_draft(bot_data, owner_user_id=111, draft=draft)
    update, query = _make_update(111, f"dupview_{draft_id}_55")
    ctx = _make_context(bot_data)

    with patch("handlers.duplicate.excel.get_expense_by_id", new=AsyncMock(return_value=None)):
        await dup.dup_view_callback(update, ctx)

    query.edit_message_text.assert_awaited()
    text = query.edit_message_text.call_args.args[0]
    assert "удал" in text.lower()
    # остаётся возможность всё равно добавить
    markup = query.edit_message_text.call_args.kwargs["reply_markup"]
    callbacks = [b.callback_data for row in markup.inline_keyboard for b in row]
    assert f"dupconfirm_{draft_id}" in callbacks


# ---------------------------------------------------------------------------
# Отметка дубликата: сценарии 14, 15
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_report_duplicate_excluded_member_denied():
    """Сценарий 14: исключённый участник (нет права просмотра) не может отметить."""
    update, query = _make_update(222, "expreport_55")
    ctx = _make_context()
    expense = {"id": 55, "user_id": "111", "project_id": 1, "amount": Decimal("100"),
               "category_name": "кафе", "description": "", "date": datetime.date.today(),
               "created_at": datetime.datetime.now(), "deleted_at": None}

    with patch("handlers.expense_notifications.excel.get_expense_by_id", new=AsyncMock(return_value=expense)), \
         patch("handlers.expense_notifications.has_permission", new=AsyncMock(return_value=False)), \
         patch("handlers.expense_notifications.duplicate_reports.create_report", new=AsyncMock()) as create_mock:
        await en.report_duplicate_callback(update, ctx)

    create_mock.assert_not_called()
    query.answer.assert_awaited()
    assert query.answer.call_args.kwargs.get("show_alert") is True


@pytest.mark.asyncio
async def test_report_duplicate_cannot_report_own_expense():
    """Нельзя отметить собственный расход дубликатом."""
    update, query = _make_update(111, "expreport_55")
    ctx = _make_context()
    expense = {"id": 55, "user_id": "111", "project_id": 1, "amount": Decimal("100"),
               "category_name": "кафе", "description": "", "date": datetime.date.today(),
               "created_at": datetime.datetime.now(), "deleted_at": None}

    with patch("handlers.expense_notifications.excel.get_expense_by_id", new=AsyncMock(return_value=expense)), \
         patch("handlers.expense_notifications.has_permission", new=AsyncMock(return_value=True)), \
         patch("handlers.expense_notifications.duplicate_reports.create_report", new=AsyncMock()) as create_mock:
        await en.report_duplicate_callback(update, ctx)

    create_mock.assert_not_called()


@pytest.mark.asyncio
async def test_report_duplicate_no_double_report():
    """Сценарий 15: повторная отметка тем же пользователем не создаётся."""
    update, query = _make_update(222, "expreport_55")
    ctx = _make_context()
    expense = {"id": 55, "user_id": "111", "project_id": 1, "amount": Decimal("100"),
               "category_name": "кафе", "description": "", "date": datetime.date.today(),
               "created_at": datetime.datetime.now(), "deleted_at": None}

    with patch("handlers.expense_notifications.excel.get_expense_by_id", new=AsyncMock(return_value=expense)), \
         patch("handlers.expense_notifications.has_permission", new=AsyncMock(return_value=True)), \
         patch("handlers.expense_notifications.duplicate_reports.has_open_report", new=AsyncMock(return_value=True)), \
         patch("handlers.expense_notifications.duplicate_reports.create_report", new=AsyncMock()) as create_mock:
        await en.report_duplicate_callback(update, ctx)

    create_mock.assert_not_called()
    assert "уже отметили" in query.answer.call_args.args[0].lower()


@pytest.mark.asyncio
async def test_report_duplicate_success_notifies_author():
    """Успешная отметка → создаётся report и уведомляется автор/владелец."""
    update, query = _make_update(222, "expreport_55")
    ctx = _make_context()
    expense = {"id": 55, "user_id": "111", "project_id": 1, "amount": Decimal("100"),
               "category_name": "кафе", "description": "", "date": datetime.date.today(),
               "created_at": datetime.datetime.now(), "deleted_at": None}

    with patch("handlers.expense_notifications.excel.get_expense_by_id", new=AsyncMock(return_value=expense)), \
         patch("handlers.expense_notifications.has_permission", new=AsyncMock(return_value=True)), \
         patch("handlers.expense_notifications.duplicate_reports.has_open_report", new=AsyncMock(return_value=False)), \
         patch("handlers.expense_notifications.duplicate_reports.create_report", new=AsyncMock(return_value=900)), \
         patch("handlers.expense_notifications.project_notifier.notify_duplicate_reported",
               new=AsyncMock(return_value={"sent": 1, "failed": 0})) as notify_mock:
        await en.report_duplicate_callback(update, ctx)

    notify_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_report_duplicate_expense_already_deleted():
    """Сценарий 18: отметка несуществующего/удалённого расхода обрабатывается мягко."""
    update, query = _make_update(222, "expreport_55")
    ctx = _make_context()
    with patch("handlers.expense_notifications.excel.get_expense_by_id", new=AsyncMock(return_value=None)):
        await en.report_duplicate_callback(update, ctx)
    query.answer.assert_awaited()
    assert query.answer.call_args.kwargs.get("show_alert") is True


# ---------------------------------------------------------------------------
# Удаление расхода: сценарий 16
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_report_delete_denied_without_permission():
    """Сценарий 16: пользователь без прав не может удалить чужой расход."""
    update, query = _make_update(222, "repdel_900_55")
    ctx = _make_context()
    # Расход чужой (автор 111), пользователь 222 без права DELETE_EXPENSE
    expense = {"id": 55, "user_id": "111", "project_id": 1, "amount": Decimal("100"),
               "category_name": "кафе", "description": "", "date": datetime.date.today(),
               "created_at": datetime.datetime.now(), "deleted_at": None}

    with patch("handlers.expense_notifications.excel.get_expense_by_id", new=AsyncMock(return_value=expense)), \
         patch("handlers.expense_notifications.has_permission", new=AsyncMock(return_value=False)), \
         patch("handlers.expense_notifications.excel.soft_delete_expense", new=AsyncMock()) as del_mock:
        await en.report_delete_callback(update, ctx)

    del_mock.assert_not_called()
    assert query.answer.call_args.kwargs.get("show_alert") is True


@pytest.mark.asyncio
async def test_report_delete_allowed_for_author():
    """Автор может удалить свой расход (soft delete) и обращение разрешается."""
    update, query = _make_update(111, "repdel_900_55")
    ctx = _make_context()
    expense = {"id": 55, "user_id": "111", "project_id": 1, "amount": Decimal("100"),
               "category_name": "кафе", "description": "", "date": datetime.date.today(),
               "created_at": datetime.datetime.now(), "deleted_at": None}

    with patch("handlers.expense_notifications.excel.get_expense_by_id", new=AsyncMock(return_value=expense)), \
         patch("handlers.expense_notifications.excel.soft_delete_expense", new=AsyncMock(return_value=True)) as del_mock, \
         patch("handlers.expense_notifications.duplicate_reports.resolve_report", new=AsyncMock(return_value=True)) as resolve_mock:
        await en.report_delete_callback(update, ctx)

    del_mock.assert_awaited_once_with(55)
    resolve_mock.assert_awaited_once()
    assert resolve_mock.call_args.args[2] == config.DuplicateReportStatus.DELETED


@pytest.mark.asyncio
async def test_report_delete_already_deleted_expense():
    """Сценарий 18: расход уже удалён — корректное сообщение, без повторного удаления."""
    update, query = _make_update(111, "repdel_900_55")
    ctx = _make_context()
    expense = {"id": 55, "user_id": "111", "project_id": 1, "amount": Decimal("100"),
               "category_name": "кафе", "description": "",
               "date": datetime.date.today(), "created_at": datetime.datetime.now(),
               "deleted_at": datetime.datetime.now()}

    with patch("handlers.expense_notifications.excel.get_expense_by_id", new=AsyncMock(return_value=expense)), \
         patch("handlers.expense_notifications.excel.soft_delete_expense", new=AsyncMock()) as del_mock:
        await en.report_delete_callback(update, ctx)

    del_mock.assert_not_called()
    text = query.edit_message_text.call_args.args[0]
    assert "удал" in text.lower()


@pytest.mark.asyncio
async def test_report_keep_marks_resolved_without_changing_expense():
    """«Оставить расход» помечает обращение KEPT, расход не трогает."""
    update, query = _make_update(111, "repkeep_900_55")
    ctx = _make_context()
    expense = {"id": 55, "user_id": "111", "project_id": 1, "amount": Decimal("100"),
               "category_name": "кафе", "description": "", "date": datetime.date.today(),
               "created_at": datetime.datetime.now(), "deleted_at": None}

    with patch("handlers.expense_notifications.excel.get_expense_by_id", new=AsyncMock(return_value=expense)), \
         patch("handlers.expense_notifications.excel.soft_delete_expense", new=AsyncMock()) as del_mock, \
         patch("handlers.expense_notifications.duplicate_reports.resolve_report", new=AsyncMock(return_value=True)) as resolve_mock:
        await en.report_keep_callback(update, ctx)

    del_mock.assert_not_called()
    assert resolve_mock.call_args.args[2] == config.DuplicateReportStatus.KEPT


# ---------------------------------------------------------------------------
# Настройки уведомлений: только сам участник, проверка доступа
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_settings_denied_for_non_member():
    """Сценарий 14: не-участник не может открыть настройки уведомлений проекта."""
    update, query = _make_update(222, "proj_notify_42")
    ctx = _make_context()
    with patch("handlers.expense_notifications.projects.is_project_member", new=AsyncMock(return_value=False)):
        await en.open_settings_menu(update, ctx)
    assert query.answer.call_args.kwargs.get("show_alert") is True


@pytest.mark.asyncio
async def test_set_notify_mode_disabled_applies_immediately():
    """Выбор DISABLED применяется сразу (без запроса порога)."""
    update, query = _make_update(111, "projnotify_set_42_disabled")
    ctx = _make_context()
    with patch("handlers.expense_notifications.projects.is_project_member", new=AsyncMock(return_value=True)), \
         patch("handlers.expense_notifications.project_notifications.set_notify_mode", new=AsyncMock(return_value=True)) as set_mock, \
         patch("handlers.expense_notifications._render_settings", new=AsyncMock()):
        ret = await en.set_notify_mode_callback(update, ctx)

    set_mock.assert_awaited_once()
    assert set_mock.call_args.args[2] == config.ExpenseNotifyMode.DISABLED


@pytest.mark.asyncio
async def test_set_notify_mode_large_only_requests_threshold():
    """Выбор LARGE_ONLY переводит в состояние ввода порога."""
    update, query = _make_update(111, "projnotify_set_42_large_only")
    ctx = _make_context()
    with patch("handlers.expense_notifications.projects.is_project_member", new=AsyncMock(return_value=True)):
        ret = await en.set_notify_mode_callback(update, ctx)

    assert ret == en.ENTERING_LARGE_THRESHOLD
    assert ctx.user_data["notify_threshold_project_id"] == 42


@pytest.mark.asyncio
async def test_threshold_input_validates_positive():
    """Порог должен быть положительным числом."""
    update = MagicMock()
    update.effective_user = MagicMock()
    update.effective_user.id = 111
    update.message = AsyncMock()
    update.message.text = "-5"
    update.message.reply_text = AsyncMock()
    ctx = _make_context()
    ctx.user_data["notify_threshold_project_id"] = 42

    with patch("handlers.expense_notifications.projects.is_project_member", new=AsyncMock(return_value=True)), \
         patch("handlers.expense_notifications.project_notifications.set_notify_mode", new=AsyncMock()) as set_mock:
        ret = await en.handle_threshold_input(update, ctx)

    set_mock.assert_not_called()
    assert ret == en.ENTERING_LARGE_THRESHOLD


@pytest.mark.asyncio
async def test_threshold_input_saves_valid_value():
    """Корректный порог сохраняется в режиме large_only."""
    update = MagicMock()
    update.effective_user = MagicMock()
    update.effective_user.id = 111
    update.message = AsyncMock()
    update.message.text = "1500"
    update.message.reply_text = AsyncMock()
    ctx = _make_context()
    ctx.user_data["notify_threshold_project_id"] = 42

    with patch("handlers.expense_notifications.projects.is_project_member", new=AsyncMock(return_value=True)), \
         patch("handlers.expense_notifications.project_notifications.set_notify_mode", new=AsyncMock(return_value=True)) as set_mock:
        ret = await en.handle_threshold_input(update, ctx)

    set_mock.assert_awaited_once()
    assert set_mock.call_args.args[2] == config.ExpenseNotifyMode.LARGE_ONLY
    assert set_mock.call_args.kwargs["large_expense_threshold"] == Decimal("1500")
