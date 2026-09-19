"""
Тесты repository слоя отметок дубликатов и настроек уведомлений (feature_110).
"""

from contextlib import asynccontextmanager
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import config
from utils import duplicate_reports, project_notifications

# --- duplicate_reports ---

@pytest.mark.asyncio
async def test_create_report_returns_id():
    with patch("utils.duplicate_reports.db.fetchval", new=AsyncMock(return_value=900)):
        report_id = await duplicate_reports.create_report(expense_id=55, reported_by_user_id=222)
    assert report_id == 900


@pytest.mark.asyncio
async def test_create_report_duplicate_returns_none():
    """ON CONFLICT DO NOTHING вернёт None — повторная отметка не создаётся (сценарий 15)."""
    with patch("utils.duplicate_reports.db.fetchval", new=AsyncMock(return_value=None)):
        report_id = await duplicate_reports.create_report(expense_id=55, reported_by_user_id=222)
    assert report_id is None


@pytest.mark.asyncio
async def test_has_open_report_true():
    with patch("utils.duplicate_reports.db.fetchval", new=AsyncMock(return_value=1)):
        assert await duplicate_reports.has_open_report(55, 222) is True


@pytest.mark.asyncio
async def test_resolve_report_updates_open_only():
    """resolve обновляет только open-обращения (защита от двойного решения)."""
    with patch("utils.duplicate_reports.db.execute", new=AsyncMock(return_value="UPDATE 1")):
        ok = await duplicate_reports.resolve_report(900, 111, config.DuplicateReportStatus.KEPT)
    assert ok is True


@pytest.mark.asyncio
async def test_resolve_report_already_resolved():
    with patch("utils.duplicate_reports.db.execute", new=AsyncMock(return_value="UPDATE 0")):
        ok = await duplicate_reports.resolve_report(900, 111, config.DuplicateReportStatus.DELETED)
    assert ok is False


@pytest.mark.asyncio
async def test_resolve_report_invalid_status():
    ok = await duplicate_reports.resolve_report(900, 111, "open")  # open недопустим как результат
    assert ok is False


# --- project_member_settings ---

@pytest.mark.asyncio
async def test_get_member_settings_default_when_absent():
    """Сценарий 11/обратная совместимость: нет строки → режим ALL."""
    with patch("utils.project_notifications.db.fetchrow", new=AsyncMock(return_value=None)):
        s = await project_notifications.get_member_settings(1, 111)
    assert s["expense_notify_mode"] == config.ExpenseNotifyMode.ALL
    assert s["large_expense_threshold"] is None


@pytest.mark.asyncio
async def test_get_member_settings_existing_row():
    row = {
        "project_id": 1, "user_id": "111",
        "expense_notify_mode": config.ExpenseNotifyMode.LARGE_ONLY,
        "large_expense_threshold": Decimal("500"),
        "updated_at": None,
    }
    with patch("utils.project_notifications.db.fetchrow", new=AsyncMock(return_value=row)):
        s = await project_notifications.get_member_settings(1, 111)
    assert s["expense_notify_mode"] == config.ExpenseNotifyMode.LARGE_ONLY
    assert s["large_expense_threshold"] == Decimal("500")


@pytest.mark.asyncio
async def test_set_notify_mode_rejects_invalid():
    ok = await project_notifications.set_notify_mode(1, 111, "bogus")
    assert ok is False


@pytest.fixture
def notification_write_context(monkeypatch):
    conn = MagicMock()
    conn.execute = AsyncMock(return_value="INSERT 0 1")

    @asynccontextmanager
    async def transaction():
        yield conn

    conn.transaction = transaction
    permission = AsyncMock()
    validate = AsyncMock()
    monkeypatch.setattr(project_notifications.db, "execute", AsyncMock())
    monkeypatch.setattr(project_notifications.db, "transaction", transaction)
    monkeypatch.setattr(project_notifications, "require_permission", permission)
    monkeypatch.setattr(project_notifications.currencies, "get_reporting_currency", AsyncMock(return_value="JPY"))
    monkeypatch.setattr(project_notifications.currencies, "validate_money_context", validate)
    return conn, permission, validate


@pytest.mark.asyncio
async def test_set_notify_mode_large_only_persists_threshold(notification_write_context):
    conn, permission, validate = notification_write_context
    ok = await project_notifications.set_notify_mode(
        1, 111, config.ExpenseNotifyMode.LARGE_ONLY, large_expense_threshold=Decimal("750"))
    assert ok is True
    permission.assert_awaited_once_with(111, 1, project_notifications.Permission.VIEW_HISTORY)
    validate.assert_awaited_once_with(conn, 111, 1, {"reporting_currency": "JPY"})
    conn.execute.assert_awaited_once()
    assert conn.execute.await_args.args[1:] == (
        1, "111", config.ExpenseNotifyMode.LARGE_ONLY, Decimal("750"), "JPY",
    )


@pytest.mark.asyncio
async def test_set_notify_mode_all_clears_threshold(notification_write_context):
    conn, permission, validate = notification_write_context
    ok = await project_notifications.set_notify_mode(
        1, 111, config.ExpenseNotifyMode.ALL, large_expense_threshold=Decimal("750"))
    assert ok is True
    permission.assert_awaited_once_with(111, 1, project_notifications.Permission.VIEW_HISTORY)
    validate.assert_awaited_once_with(conn, 111, 1, {"reporting_currency": "JPY"})
    conn.execute.assert_awaited_once()
    assert conn.execute.await_args.args[1:] == (
        1, "111", config.ExpenseNotifyMode.ALL, None, None,
    )


@pytest.mark.asyncio
async def test_set_notify_mode_denied_member_does_not_write(notification_write_context):
    conn, permission, validate = notification_write_context
    permission.side_effect = PermissionError("not a member")
    ok = await project_notifications.set_notify_mode(
        1, 111, config.ExpenseNotifyMode.LARGE_ONLY, large_expense_threshold=Decimal("750"))
    assert ok is False
    conn.execute.assert_not_awaited()
    validate.assert_not_awaited()
