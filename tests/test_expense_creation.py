"""
Тесты идемпотентного создания расхода и оркестрации process_new_expense
(feature_110).

Покрывают обязательные сценарии ТЗ:
 7.  Пользователь подтверждает создание — создаётся одна операция.
 8.  Пользователь дважды нажимает callback — операция остаётся одна.
 9.  Пользователь отменяет создание — операция не создаётся.
 17. Два параллельных подтверждения не создают два расхода (идемпотентность).
"""

import asyncio
import datetime
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from utils import expense_creation, duplicate_service


class FakeConn:
    """Мок asyncpg-соединения с поддержкой вложенной транзакции."""
    def __init__(self, new_id=777):
        self.new_id = new_id
        self.executed = []

    async def execute(self, sql, *args):
        self.executed.append((sql, args))
        return "INSERT 0 1"

    async def fetchval(self, sql, *args):
        # эмулируем RETURNING id
        return self.new_id

    def transaction(self):
        conn = self

        class _Tx:
            async def __aenter__(self_inner):
                return conn

            async def __aexit__(self_inner, *a):
                return False

        return _Tx()


def _patch_transaction(conn):
    """Подменяет db.transaction() так, чтобы он отдавал FakeConn."""
    @asynccontextmanager
    async def _cm():
        yield conn
    return patch("utils.excel.db.transaction", side_effect=lambda: _cm())


@pytest.mark.asyncio
async def test_create_expense_idempotent_creates_once():
    """Сценарий 7: одно создание → один расход."""
    conn = FakeConn(new_id=501)
    bot_data = {}
    with _patch_transaction(conn):
        result = await duplicate_service.create_expense_idempotent(
            author_id=111, amount=1000, category_id=5, description="кофе",
            project_id=1, idempotency_key="draft-abc", bot_data=bot_data,
        )

    assert result["created"] is True
    assert result["expense_id"] == 501
    # ключ закэширован
    assert bot_data["expense_idempotency"]["draft-abc"] == 501


@pytest.mark.asyncio
async def test_create_expense_idempotent_second_call_no_duplicate():
    """Сценарий 8: повторный вызов с тем же ключом не создаёт второй расход."""
    conn = FakeConn(new_id=502)
    bot_data = {}
    with _patch_transaction(conn):
        first = await duplicate_service.create_expense_idempotent(
            author_id=111, amount=1000, category_id=5, description="",
            project_id=1, idempotency_key="draft-x", bot_data=bot_data,
        )
        second = await duplicate_service.create_expense_idempotent(
            author_id=111, amount=1000, category_id=5, description="",
            project_id=1, idempotency_key="draft-x", bot_data=bot_data,
        )

    assert first["created"] is True
    assert second["created"] is False  # второй раз не создаём
    assert second["expense_id"] == 502


@pytest.mark.asyncio
async def test_confirm_pending_expense_creates_once_then_already():
    """
    Сценарий 8/17: первое подтверждение создаёт расход, второе (двойное нажатие /
    параллельный запрос) возвращает already и НЕ создаёт второй.
    """
    conn = FakeConn(new_id=600)
    bot_data = {}
    # Подготавливаем черновик
    draft = {
        "author_id": "111", "amount": 1000, "category_id": 5,
        "category_name": "кафе", "description": "обед", "project_id": 1,
    }
    draft_id = expense_creation._store_draft(bot_data, 111, draft)

    with _patch_transaction(conn), \
         patch("utils.expense_creation.project_notifier.notify_expense_created",
               new=AsyncMock(return_value={"sent": 0, "failed": 0, "skipped": 0})):
        first = await expense_creation.confirm_pending_expense(
            None, draft_id=draft_id, bot_data=bot_data
        )
        second = await expense_creation.confirm_pending_expense(
            None, draft_id=draft_id, bot_data=bot_data
        )
        # дождёмся фоновых задач уведомления
        await asyncio.sleep(0)

    assert first["status"] == "created"
    assert first["expense_id"] == 600
    assert second["status"] == "already"
    assert second["expense_id"] == 600


@pytest.mark.asyncio
async def test_confirm_pending_expense_expired_draft():
    """Сценарий 9 (вариант): отсутствующий черновик → expired, расход не создаётся."""
    result = await expense_creation.confirm_pending_expense(
        None, draft_id="does-not-exist", bot_data={}
    )
    assert result["status"] == "expired"
    assert result["expense_id"] is None


@pytest.mark.asyncio
async def test_concurrent_confirmations_create_single_expense():
    """
    Сценарий 17: два параллельных подтверждения одного черновика создают
    только один расход (idempotency key защищает от гонки в пределах процесса).
    """
    conn = FakeConn(new_id=900)
    bot_data = {}
    draft = {
        "author_id": "111", "amount": 500, "category_id": 3,
        "category_name": "такси", "description": "", "project_id": 1,
    }
    draft_id = expense_creation._store_draft(bot_data, 111, draft)

    fetchval_calls = {"n": 0}

    async def counting_fetchval(sql, *args):
        fetchval_calls["n"] += 1
        return 900

    conn.fetchval = counting_fetchval

    with _patch_transaction(conn), \
         patch("utils.expense_creation.project_notifier.notify_expense_created",
               new=AsyncMock(return_value={"sent": 0, "failed": 0, "skipped": 0})):
        results = await asyncio.gather(
            expense_creation.confirm_pending_expense(None, draft_id=draft_id, bot_data=bot_data),
            expense_creation.confirm_pending_expense(None, draft_id=draft_id, bot_data=bot_data),
        )
        await asyncio.sleep(0)

    statuses = sorted(r["status"] for r in results)
    # Ровно одно "created", второе — "already"
    assert statuses == ["already", "created"]
    # INSERT выполнен ровно один раз
    assert fetchval_calls["n"] == 1


@pytest.mark.asyncio
async def test_process_new_expense_no_check_creates_immediately():
    """Если проверка дубликатов не нужна (личный расход) — создаётся сразу."""
    conn = FakeConn(new_id=42)
    bot_data = {}
    with _patch_transaction(conn), \
         patch("utils.expense_creation.duplicate_service.should_check_duplicates",
               new=AsyncMock(return_value=False)):
        outcome = await expense_creation.process_new_expense(
            None, author_id=111, amount=100, category_id=5, category_name="кафе",
            description="", project_id=None, bot_data=bot_data,
        )

    assert outcome["status"] == "created"
    assert outcome["expense_id"] == 42


@pytest.mark.asyncio
async def test_process_new_expense_duplicate_returns_draft():
    """Найден дубль → расход НЕ создан, возвращается draft_id и existing."""
    bot_data = {}
    existing = {"id": 55, "author_id": "999", "amount": 1000,
                "category_name": "кафе", "description": "обед",
                "date": datetime.date.today(),
                "created_at": datetime.datetime.now()}

    with patch("utils.expense_creation.duplicate_service.should_check_duplicates",
               new=AsyncMock(return_value=True)), \
         patch("utils.expense_creation.duplicate_service.find_possible_duplicate",
               new=AsyncMock(return_value=existing)):
        outcome = await expense_creation.process_new_expense(
            None, author_id=111, amount=1000, category_id=5, category_name="кафе",
            description="обед", project_id=1, bot_data=bot_data,
        )

    assert outcome["status"] == "duplicate"
    assert "draft_id" in outcome
    assert outcome["existing"]["id"] == 55
    # черновик сохранён в bot_data
    assert expense_creation.get_draft(bot_data, outcome["draft_id"]) is not None


@pytest.mark.asyncio
async def test_process_new_expense_notifies_on_project_creation():
    """При создании расхода в проекте запускается уведомление участников."""
    conn = FakeConn(new_id=70)
    bot_data = {}
    notify_mock = AsyncMock(return_value={"sent": 1, "failed": 0, "skipped": 0})

    with _patch_transaction(conn), \
         patch("utils.expense_creation.duplicate_service.should_check_duplicates",
               new=AsyncMock(return_value=True)), \
         patch("utils.expense_creation.duplicate_service.find_possible_duplicate",
               new=AsyncMock(return_value=None)), \
         patch("utils.expense_creation.project_notifier.notify_expense_created", new=notify_mock):
        outcome = await expense_creation.process_new_expense(
            None, author_id=111, amount=1000, category_id=5, category_name="кафе",
            description="", project_id=1, bot_data=bot_data,
        )
        await asyncio.sleep(0)  # дать запуститься фоновой задаче

    assert outcome["status"] == "created"
    notify_mock.assert_awaited_once()
