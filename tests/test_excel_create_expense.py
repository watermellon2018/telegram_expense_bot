"""
Тесты новых функций utils/excel.py (feature_110) и обратной совместимости.

Сценарий 11 (обратная совместимость): личный расход (project_id=None) создаётся
как раньше, без проверки дубликатов и без уведомлений.
"""

from unittest.mock import AsyncMock, patch

import pytest

from utils import excel


@pytest.mark.asyncio
async def test_create_expense_returns_id():
    with patch("utils.excel.db.fetchval", new=AsyncMock(return_value=321)):
        expense_id = await excel.create_expense(
            user_id=111, amount=100, category_id=5, description="кофе", project_id=None)
    assert expense_id == 321


@pytest.mark.asyncio
async def test_create_expense_uses_conn_when_provided():
    conn = AsyncMock()
    conn.fetchval = AsyncMock(return_value=999)
    expense_id = await excel.create_expense(
        user_id=111, amount=100, category_id=5, description="", project_id=1, conn=conn)
    assert expense_id == 999
    conn.fetchval.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_expense_by_id_excludes_deleted_by_default():
    captured = {}

    async def fake_fetchrow(sql, *args):
        captured["sql"] = sql
        return None

    with patch("utils.excel.db.fetchrow", new=fake_fetchrow):
        await excel.get_expense_by_id(55)
    assert "deleted_at IS NULL" in captured["sql"]


@pytest.mark.asyncio
async def test_get_expense_by_id_include_deleted():
    captured = {}

    async def fake_fetchrow(sql, *args):
        captured["sql"] = sql
        return None

    with patch("utils.excel.db.fetchrow", new=fake_fetchrow):
        await excel.get_expense_by_id(55, include_deleted=True)
    assert "deleted_at IS NULL" not in captured["sql"]


@pytest.mark.asyncio
async def test_soft_delete_expense_success():
    with patch("utils.excel.db.execute", new=AsyncMock(return_value="UPDATE 1")):
        assert await excel.soft_delete_expense(55) is True


@pytest.mark.asyncio
async def test_soft_delete_expense_already_deleted():
    with patch("utils.excel.db.execute", new=AsyncMock(return_value="UPDATE 0")):
        assert await excel.soft_delete_expense(55) is False


@pytest.mark.asyncio
async def test_acquire_project_expense_lock_calls_advisory():
    conn = AsyncMock()
    conn.execute = AsyncMock()
    await excel.acquire_project_expense_lock(conn, 7)
    conn.execute.assert_awaited_once()
    sql = conn.execute.call_args.args[0]
    assert "pg_advisory_xact_lock" in sql


# --- Обратная совместимость add_expense (личный расход) ---

@pytest.mark.asyncio
async def test_add_expense_personal_still_works():
    """Сценарий 11: личный расход через старый add_expense не сломан."""
    category = {"category_id": 5, "name": "кафе", "project_id": None}
    # add_expense импортирует utils.categories локально, поэтому патчим источник
    with patch("utils.excel.db.execute", new=AsyncMock()) as exec_mock, \
         patch("utils.categories.get_category_by_id", new=AsyncMock(return_value=category)):
        ok = await excel.add_expense(user_id=111, amount=100, category_id=5,
                                     description="кофе", project_id=None)
    assert ok is True
    # был вызван INSERT расхода
    assert exec_mock.await_count >= 1
