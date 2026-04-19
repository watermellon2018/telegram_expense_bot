"""
Тесты агрегации расходов по участникам в utils/excel.py
"""
import pytest
from unittest.mock import AsyncMock, patch

from utils import excel


@pytest.mark.asyncio
async def test_get_month_expenses_project_aggregates_by_participant():
    """В project-режиме month-статистика должна агрегироваться по e.user_id."""
    rows = [
        {"amount": 100.0, "category": "продукты", "user_id": "1"},
        {"amount": 50.0, "category": "транспорт", "user_id": "2"},
        {"amount": 25.0, "category": "продукты", "user_id": "1"},
        {"amount": 10.0, "category": "прочее", "user_id": None},
    ]

    with patch("utils.permissions.has_permission", new=AsyncMock(return_value=True)), \
         patch("utils.excel.db.fetch", new=AsyncMock(return_value=rows)):
        result = await excel.get_month_expenses(user_id=123, month=4, year=2026, project_id=42)

    assert result["count"] == 4
    assert result["total"] == pytest.approx(185.0)
    assert result["by_category"]["продукты"] == pytest.approx(125.0)
    assert result["by_participant"]["ID: 1"] == pytest.approx(125.0)
    assert result["by_participant"]["ID: 2"] == pytest.approx(50.0)
    assert result["by_participant"]["Неизвестный участник"] == pytest.approx(10.0)


@pytest.mark.asyncio
async def test_get_day_expenses_project_aggregates_by_participant():
    """В project-режиме day-статистика должна агрегироваться по e.user_id."""
    rows = [
        {"amount": 70.0, "category": "продукты", "user_id": "1"},
        {"amount": 30.0, "category": "транспорт", "user_id": "2"},
        {"amount": 20.0, "category": "продукты", "user_id": "1"},
    ]

    with patch("utils.permissions.has_permission", new=AsyncMock(return_value=True)), \
         patch("utils.excel.db.fetch", new=AsyncMock(return_value=rows)):
        result = await excel.get_day_expenses(user_id=123, date="2026-04-19", project_id=42)

    assert result["status"] is True
    assert result["count"] == 3
    assert result["total"] == pytest.approx(120.0)
    assert result["by_participant"]["ID: 1"] == pytest.approx(90.0)
    assert result["by_participant"]["ID: 2"] == pytest.approx(30.0)


@pytest.mark.asyncio
async def test_get_month_expenses_personal_has_no_participants_breakdown():
    """В personal-режиме должен возвращаться пустой by_participant."""
    rows = [
        {"amount": 100.0, "category": "продукты"},
    ]

    with patch("utils.excel.db.fetch", new=AsyncMock(return_value=rows)):
        result = await excel.get_month_expenses(user_id=123, month=4, year=2026, project_id=None)

    assert result["total"] == pytest.approx(100.0)
    assert result["by_participant"] == {}


@pytest.mark.asyncio
async def test_get_day_expenses_permission_denied_has_stable_shape():
    """При отсутствии прав day-ответ должен содержать by_participant."""
    with patch("utils.permissions.has_permission", new=AsyncMock(return_value=False)):
        result = await excel.get_day_expenses(user_id=123, date="2026-04-19", project_id=42)

    assert result == {
        "status": True,
        "total": 0,
        "by_category": {},
        "by_participant": {},
        "count": 0,
    }

