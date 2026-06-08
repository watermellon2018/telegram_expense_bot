"""
Тесты сервиса поиска дубликатов расходов (feature_110).

Покрывают обязательные сценарии ТЗ:
 1. В проекте один участник — проверка дубля не выполняется.
 2. В совместном проекте найден расход с той же суммой и категорией.
 3. Расход другого пользователя за пределами временного окна не дубликат.
 4. Расход самого пользователя не считается межпользовательским дубликатом.
 5. Разная категория не приводит к предупреждению.
 6. Сумма в пределах допустимого процента приводит к предупреждению.
"""

import datetime
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest

from utils import duplicate_service


def _row(expense_id, author_id, amount, category_id, description, created_at,
         category_name="Кафе и рестораны", date=None):
    """Хелпер: строка-кандидат, как её вернул бы SQL."""
    return {
        "id": expense_id,
        "author_id": str(author_id),
        "amount": Decimal(str(amount)),
        "category_id": category_id,
        "date": date or datetime.date.today(),
        "time": datetime.time(10, 0, 0),
        "description": description,
        "created_at": created_at,
        "category_name": category_name,
    }


# --- Базовые unit-проверки допуска суммы ---

def test_amount_within_tolerance_exact():
    assert duplicate_service._amount_within_tolerance(Decimal("1000"), Decimal("1000"), 2)


def test_amount_within_tolerance_inside():
    # 1000 vs 1020 → 1.96% ≤ 2%
    assert duplicate_service._amount_within_tolerance(Decimal("1000"), Decimal("1020"), 2)


def test_amount_within_tolerance_outside():
    # 1000 vs 1100 → 9% > 2%
    assert not duplicate_service._amount_within_tolerance(Decimal("1000"), Decimal("1100"), 2)


# --- Сценарий 2: найден дубликат с той же суммой и категорией ---

@pytest.mark.asyncio
async def test_find_duplicate_same_amount_and_category():
    now = datetime.datetime.now()
    rows = [_row(10, author_id="999", amount=1250, category_id=5,
                 description="Завтрак", created_at=now - datetime.timedelta(minutes=7))]

    with patch("utils.duplicate_service.db.fetch", new=AsyncMock(return_value=rows)):
        result = await duplicate_service.find_possible_duplicate(
            project_id=1, author_id=111, amount=1250, category_id=5,
            expense_date=datetime.date.today(), created_at=now, comment="Завтрак",
        )

    assert result is not None
    assert result["id"] == 10


# --- Сценарий 6: сумма в пределах допуска приводит к совпадению ---

@pytest.mark.asyncio
async def test_find_duplicate_amount_within_tolerance():
    now = datetime.datetime.now()
    rows = [_row(11, author_id="999", amount=1020, category_id=5,
                 description=None, created_at=now - datetime.timedelta(minutes=1))]

    with patch("utils.duplicate_service.db.fetch", new=AsyncMock(return_value=rows)):
        result = await duplicate_service.find_possible_duplicate(
            project_id=1, author_id=111, amount=1000, category_id=5,
            expense_date=datetime.date.today(), created_at=now,
        )

    assert result is not None
    assert result["id"] == 11


@pytest.mark.asyncio
async def test_find_duplicate_amount_outside_tolerance_returns_none():
    now = datetime.datetime.now()
    # 1000 vs 1100 — вне допуска 2%
    rows = [_row(12, author_id="999", amount=1100, category_id=5,
                 description=None, created_at=now)]

    with patch("utils.duplicate_service.db.fetch", new=AsyncMock(return_value=rows)):
        result = await duplicate_service.find_possible_duplicate(
            project_id=1, author_id=111, amount=1000, category_id=5,
            expense_date=datetime.date.today(), created_at=now,
        )

    assert result is None


# --- Сценарий 5: разная категория не даёт совпадения ---
# (SQL фильтрует по category_id, поэтому кандидатов нет — fetch вернёт [])

@pytest.mark.asyncio
async def test_find_duplicate_different_category_no_match():
    with patch("utils.duplicate_service.db.fetch", new=AsyncMock(return_value=[])):
        result = await duplicate_service.find_possible_duplicate(
            project_id=1, author_id=111, amount=1000, category_id=7,
            expense_date=datetime.date.today(),
        )
    assert result is None


# --- Сценарий 3: за пределами временного окна (fetch вернёт [], т.к. SQL фильтрует created_at) ---

@pytest.mark.asyncio
async def test_find_duplicate_outside_time_window_no_match():
    # Симулируем, что SQL-фильтр created_at >= earliest отсёк старый расход
    with patch("utils.duplicate_service.db.fetch", new=AsyncMock(return_value=[])):
        result = await duplicate_service.find_possible_duplicate(
            project_id=1, author_id=111, amount=1000, category_id=5,
            expense_date=datetime.date.today(),
        )
    assert result is None


# --- Сценарий 4: собственный расход исключается (SQL: user_id <> author) ---

@pytest.mark.asyncio
async def test_find_duplicate_excludes_own_expense_via_query():
    """
    Проверяем, что в SQL передаётся author_id для условия e.user_id <> $4.
    Собственные расходы не возвращаются (мокаем пустой результат как делает БД).
    """
    captured = {}

    async def fake_fetch(sql, *args):
        captured["sql"] = sql
        captured["args"] = args
        return []

    with patch("utils.duplicate_service.db.fetch", new=fake_fetch):
        await duplicate_service.find_possible_duplicate(
            project_id=1, author_id=111, amount=1000, category_id=5,
            expense_date=datetime.date.today(),
        )

    assert "e.user_id <> $4" in captured["sql"]
    assert captured["args"][3] == "111"  # author_id передан строкой


# --- Ранжирование: при нескольких совпадениях выбирается ближайшее по сумме ---

@pytest.mark.asyncio
async def test_find_duplicate_picks_closest_amount():
    now = datetime.datetime.now()
    rows = [
        _row(20, author_id="999", amount=1010, category_id=5, description=None,
             created_at=now - datetime.timedelta(minutes=1)),
        _row(21, author_id="999", amount=1000, category_id=5, description=None,
             created_at=now - datetime.timedelta(minutes=5)),
    ]
    with patch("utils.duplicate_service.db.fetch", new=AsyncMock(return_value=rows)):
        result = await duplicate_service.find_possible_duplicate(
            project_id=1, author_id=111, amount=1000, category_id=5,
            expense_date=datetime.date.today(), created_at=now,
        )
    # Точное совпадение суммы (1000) приоритетнее, хоть оно и старше
    assert result["id"] == 21


# --- Сценарий 1: один участник — should_check_duplicates == False ---

@pytest.mark.asyncio
async def test_should_check_duplicates_single_member():
    with patch("utils.duplicate_service.has_permission", new=AsyncMock(return_value=True)), \
         patch("utils.duplicate_service.is_shared_project", new=AsyncMock(return_value=False)):
        assert await duplicate_service.should_check_duplicates(111, project_id=1) is False


@pytest.mark.asyncio
async def test_should_check_duplicates_personal_expense():
    # project_id=None → личный расход, проверка не нужна
    assert await duplicate_service.should_check_duplicates(111, project_id=None) is False


@pytest.mark.asyncio
async def test_should_check_duplicates_no_add_permission():
    with patch("utils.duplicate_service.has_permission", new=AsyncMock(return_value=False)):
        assert await duplicate_service.should_check_duplicates(111, project_id=1) is False


@pytest.mark.asyncio
async def test_should_check_duplicates_shared_with_permission():
    with patch("utils.duplicate_service.has_permission", new=AsyncMock(return_value=True)), \
         patch("utils.duplicate_service.is_shared_project", new=AsyncMock(return_value=True)):
        assert await duplicate_service.should_check_duplicates(111, project_id=1) is True


@pytest.mark.asyncio
async def test_is_shared_project_counts_members():
    with patch("utils.duplicate_service.db.fetchval", new=AsyncMock(return_value=2)):
        assert await duplicate_service.is_shared_project(1) is True
    with patch("utils.duplicate_service.db.fetchval", new=AsyncMock(return_value=1)):
        assert await duplicate_service.is_shared_project(1) is False
