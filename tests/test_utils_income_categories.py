"""Тесты для utils/income_categories.py"""

import pytest
from unittest.mock import AsyncMock, patch

from utils import income_categories


@pytest.mark.asyncio
async def test_create_income_category_duplicate_active():
    """Активный дубль категории не должен создаваться повторно."""
    with patch("utils.income_categories.db.execute", new=AsyncMock()), \
         patch("utils.income_categories.db.fetchrow", new=AsyncMock(side_effect=[
             {"income_category_id": 10, "name": "Зарплата"},
             None,
         ])):
        result = await income_categories.create_income_category(1, "  зарплата  ", None, False)

    assert result["success"] is False
    assert "уже существует" in result["message"].lower()


@pytest.mark.asyncio
async def test_create_income_category_reactivate_inactive():
    """Неактивный дубль категории должен реактивироваться."""
    with patch("utils.income_categories.db.execute", new=AsyncMock()), \
         patch("utils.income_categories.db.fetchrow", new=AsyncMock(side_effect=[
             None,
             {"income_category_id": 77},
         ])):
        result = await income_categories.create_income_category(1, " Зарплата ", None, False)

    assert result["success"] is True
    assert result["income_category_id"] == 77
    assert "восстановлена" in result["message"].lower()


def test_normalize_category_name():
    """Имя категории должно нормализоваться по trim/collapse/case-insensitive правилам."""
    normalized = income_categories.normalize_category_name("  ЗаРпЛаТа   в  офисе  ")
    assert normalized == "зарплата в офисе"


@pytest.mark.asyncio
async def test_deactivate_income_category_blocked_by_active_recurring():
    """Деактивация должна блокироваться, если есть активный recurring income."""
    category = {
        "income_category_id": 11,
        "name": "Премия",
        "is_system": False,
        "project_id": None,
        "is_active": True,
        "created_at": None,
    }
    with patch("utils.income_categories.get_income_category_by_id", new=AsyncMock(return_value=category)), \
         patch("utils.income_categories.db.fetchval", new=AsyncMock(return_value=2)), \
         patch("utils.income_categories.db.execute", new=AsyncMock()):
        result = await income_categories.deactivate_income_category(1, 11)

    assert result["success"] is False
    assert "постоянного дохода" in result["message"].lower()
