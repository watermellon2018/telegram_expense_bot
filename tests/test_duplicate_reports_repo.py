"""
Тесты repository слоя отметок дубликатов и настроек уведомлений (feature_110).
"""

from decimal import Decimal
from unittest.mock import AsyncMock, patch

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


@pytest.mark.asyncio
async def test_set_notify_mode_large_only_persists_threshold():
    executed = []

    async def fake_execute(sql, *args):
        executed.append((sql, args))
        return "INSERT 0 1"

    with patch("utils.project_notifications.db.execute", new=fake_execute):
        ok = await project_notifications.set_notify_mode(
            1, 111, config.ExpenseNotifyMode.LARGE_ONLY, large_expense_threshold=Decimal("750"))
    assert ok is True
    # последний execute — это upsert настроек; порог 750.0 присутствует среди args
    upsert_args = executed[-1][1]
    assert 750.0 in upsert_args


@pytest.mark.asyncio
async def test_set_notify_mode_all_clears_threshold():
    executed = []

    async def fake_execute(sql, *args):
        executed.append((sql, args))
        return "INSERT 0 1"

    with patch("utils.project_notifications.db.execute", new=fake_execute):
        ok = await project_notifications.set_notify_mode(
            1, 111, config.ExpenseNotifyMode.ALL, large_expense_threshold=Decimal("750"))
    assert ok is True
    # для режима ALL порог должен быть None (обнулён)
    upsert_args = executed[-1][1]
    assert None in upsert_args
