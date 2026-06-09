"""
Тесты фичи «шаблоны категорий для проектов»:
- изоляция категорий проекта (categories_isolated) в utils/categories.py;
- хелпер эмодзи get_category_emoji;
- создание проекта по шаблону в utils/projects.py (копирование категорий,
  флаг изоляции, атомарность транзакции, вынос makedirs за commit).

БД мокается; реального соединения нет. Логика изоляции живёт в SQL, поэтому для
функций чтения проверяем, что запрос содержит изоляционное условие и корректные
биндинги; поведенческие проверки (копирование/откат) — на create_project, где
реальная Python-логика.
"""
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch

import pytest

import config
from utils import categories, projects


# --------------------------------------------------------------------------- #
# get_category_emoji
# --------------------------------------------------------------------------- #
def test_get_category_emoji_default_category():
    """Дефолтная категория → её эмодзи из DEFAULT_CATEGORIES."""
    assert categories.get_category_emoji("продукты") == config.DEFAULT_CATEGORIES["продукты"]


def test_get_category_emoji_template_category():
    """Категория из шаблона проекта → эмодзи шаблона, а не 📦."""
    # «перелёт» есть только в шаблоне vacation, не в DEFAULT_CATEGORIES
    assert "перелёт" not in config.DEFAULT_CATEGORIES
    assert categories.get_category_emoji("перелёт") == "✈️"
    assert categories.get_category_emoji("стройматериалы") == "🧱"


def test_get_category_emoji_unknown_category():
    """Неизвестная категория → нейтральная иконка."""
    assert categories.get_category_emoji("несуществующая-категория-xyz") == "📦"


# --------------------------------------------------------------------------- #
# get_categories_for_user_project — изоляция
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_get_categories_project_query_has_isolation_clause():
    """Запрос категорий проекта учитывает флаг изоляции и джойнит projects."""
    fetch_mock = AsyncMock(return_value=[])
    with patch("utils.categories.db.fetch", new=fetch_mock), \
         patch("utils.permissions.has_permission", new=AsyncMock(return_value=True)):
        await categories.get_categories_for_user_project(user_id=1, project_id=42)

    sql, args = fetch_mock.call_args.args[0], fetch_mock.call_args.args[1:]
    assert "JOIN projects p" in sql
    assert "categories_isolated" in sql
    assert args == (42,)


@pytest.mark.asyncio
async def test_get_categories_isolated_project_returns_only_project_cats():
    """
    В изолированном проекте подмешивания глобальных не происходит: функция
    отдаёт ровно то, что вернул SQL (а SQL отфильтровал глобальные).
    """
    project_cats = [
        {"category_id": 1, "name": "перелёт", "is_system": False,
         "is_active": True, "project_id": 42, "created_at": None},
        {"category_id": 2, "name": "жильё", "is_system": False,
         "is_active": True, "project_id": 42, "created_at": None},
    ]
    with patch("utils.categories.db.fetch", new=AsyncMock(return_value=project_cats)), \
         patch("utils.permissions.has_permission", new=AsyncMock(return_value=True)):
        result = await categories.get_categories_for_user_project(user_id=1, project_id=42)

    assert {c["project_id"] for c in result} == {42}
    assert all(c["project_id"] is not None for c in result)


@pytest.mark.asyncio
async def test_get_categories_personal_branch_unchanged():
    """Личный режим (project_id=None) не джойнит projects (ветка не тронута)."""
    fetch_mock = AsyncMock(return_value=[])
    with patch("utils.categories.db.fetch", new=fetch_mock):
        await categories.get_categories_for_user_project(user_id=1, project_id=None)

    sql = fetch_mock.call_args.args[0]
    assert "JOIN projects" not in sql
    assert "project_id IS NULL" in sql


# --------------------------------------------------------------------------- #
# get_category_by_name — изоляция
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_get_category_by_name_project_query_has_isolation_clause():
    """Резолв имени в проекте учитывает изоляцию и джойнит projects."""
    fetchrow_mock = AsyncMock(return_value=None)
    with patch("utils.categories.db.fetchrow", new=fetchrow_mock):
        await categories.get_category_by_name(user_id=1, name="продукты", project_id=42)

    sql, args = fetchrow_mock.call_args.args[0], fetchrow_mock.call_args.args[1:]
    assert "JOIN projects p" in sql
    assert "categories_isolated" in sql
    assert args == ("продукты", 42)


@pytest.mark.asyncio
async def test_get_category_by_name_isolated_global_not_found():
    """
    В изолированном проекте имя глобальной категории не резолвится:
    SQL вернул None → функция вернула None.
    """
    with patch("utils.categories.db.fetchrow", new=AsyncMock(return_value=None)):
        result = await categories.get_category_by_name(user_id=1, name="продукты", project_id=42)

    assert result is None


@pytest.mark.asyncio
async def test_get_category_by_name_project_cat_found():
    """Имя категории проекта резолвится корректно."""
    row = {"category_id": 5, "name": "перелёт", "is_system": False,
           "is_active": True, "project_id": 42, "created_at": None}
    with patch("utils.categories.db.fetchrow", new=AsyncMock(return_value=row)):
        result = await categories.get_category_by_name(user_id=1, name="перелёт", project_id=42)

    assert result is not None
    assert result["category_id"] == 5
    assert result["project_id"] == 42


# --------------------------------------------------------------------------- #
# create_project — шаблоны, флаг изоляции, копирование, атомарность
# --------------------------------------------------------------------------- #
class FakeConn:
    """Мок asyncpg-соединения с поддержкой вложенной транзакции (как в репозитории)."""

    def __init__(self, new_project_id=100, fail_on_category_index=None):
        self.new_project_id = new_project_id
        # если задан — execute с INSERT INTO categories на этом по счёту вызове бросит
        self.fail_on_category_index = fail_on_category_index
        self.executed = []
        self._category_inserts = 0
        self.tx_committed = None  # True если транзакция вышла без исключения

    async def fetchrow(self, sql, *args):
        self.executed.append((sql, args))
        if "INSERT INTO projects" in sql:
            return {"project_id": self.new_project_id}
        return None

    async def execute(self, sql, *args):
        self.executed.append((sql, args))
        if "INSERT INTO categories" in sql:
            self._category_inserts += 1
            if (self.fail_on_category_index is not None
                    and self._category_inserts == self.fail_on_category_index):
                raise RuntimeError("boom: category insert failed")
        return "INSERT 0 1"

    def transaction(self):
        conn = self

        class _Tx:
            async def __aenter__(self_inner):
                return conn

            async def __aexit__(self_inner, exc_type, *a):
                conn.tx_committed = exc_type is None
                return False  # не глушим исключение

        return _Tx()

    def category_insert_count(self):
        return sum(1 for sql, _ in self.executed if "INSERT INTO categories" in sql)


def _patch_project_transaction(conn):
    """db.transaction() в utils.projects отдаёт FakeConn."""
    @asynccontextmanager
    async def _cm():
        yield conn
    return patch("utils.projects.db.transaction", side_effect=lambda: _cm())


@pytest.mark.asyncio
async def test_create_project_without_template_not_isolated():
    """Обычный проект (template_key=None): isolated=FALSE, категории не копируются."""
    conn = FakeConn(new_project_id=100)
    with patch("utils.projects.db.execute", new=AsyncMock()), \
         patch("utils.projects.db.fetchrow", new=AsyncMock(return_value=None)), \
         _patch_project_transaction(conn), \
         patch("utils.projects.os.makedirs"), \
         patch("utils.excel.create_user_dir", return_value="/tmp/u"):
        result = await projects.create_project(1, "Поездка", template_key=None)

    assert result["success"] is True
    assert result["categories_isolated"] is False
    assert conn.category_insert_count() == 0
    # в INSERT projects флаг изоляции = False
    proj_insert = next(a for sql, a in conn.executed if "INSERT INTO projects" in sql)
    assert proj_insert[-1] is False


@pytest.mark.asyncio
async def test_create_project_with_template_copies_categories_and_isolates():
    """Тематический шаблон: isolated=TRUE, копируются ровно категории шаблона."""
    conn = FakeConn(new_project_id=200)
    expected = list(config.PROJECT_TEMPLATES["vacation"]["categories"].keys())

    with patch("utils.projects.db.execute", new=AsyncMock()), \
         patch("utils.projects.db.fetchrow", new=AsyncMock(return_value=None)), \
         _patch_project_transaction(conn), \
         patch("utils.projects.os.makedirs"), \
         patch("utils.excel.create_user_dir", return_value="/tmp/u"):
        result = await projects.create_project(1, "Отпуск", template_key="vacation")

    assert result["success"] is True
    assert result["categories_isolated"] is True
    assert conn.category_insert_count() == len(expected)

    # имена категорий ровно из шаблона, project_id новый, user_id владельца
    inserted_names = [a[2] for sql, a in conn.executed if "INSERT INTO categories" in sql]
    assert inserted_names == expected
    for sql, a in conn.executed:
        if "INSERT INTO categories" in sql:
            assert a[0] == "1"        # user_id владельца
            assert a[1] == 200        # project_id нового проекта

    # в INSERT projects флаг изоляции = True
    proj_insert = next(a for sql, a in conn.executed if "INSERT INTO projects" in sql)
    assert proj_insert[-1] is True


@pytest.mark.asyncio
async def test_create_project_unknown_template_fails_without_creating():
    """Неизвестный шаблон → success=False, проект не создаётся."""
    conn = FakeConn()
    with patch("utils.projects.db.execute", new=AsyncMock()), \
         patch("utils.projects.db.fetchrow", new=AsyncMock(return_value=None)), \
         _patch_project_transaction(conn), \
         patch("utils.projects.os.makedirs"), \
         patch("utils.excel.create_user_dir", return_value="/tmp/u"):
        result = await projects.create_project(1, "Тест", template_key="не-существует")

    assert result["success"] is False
    assert conn.executed == []  # транзакция не начиналась


@pytest.mark.asyncio
async def test_create_project_atomic_rollback_on_category_failure():
    """
    Ключевой тест атомарности: падение на копировании категории пробрасывает
    исключение из транзакции (откат), makedirs НЕ вызывается.
    """
    conn = FakeConn(new_project_id=300, fail_on_category_index=2)
    makedirs_mock = AsyncMock()
    with patch("utils.projects.db.execute", new=AsyncMock()), \
         patch("utils.projects.db.fetchrow", new=AsyncMock(return_value=None)), \
         _patch_project_transaction(conn), \
         patch("utils.projects.os.makedirs", new=makedirs_mock), \
         patch("utils.excel.create_user_dir", return_value="/tmp/u"):
        with pytest.raises(RuntimeError):
            await projects.create_project(1, "Отпуск", template_key="vacation")

    # транзакция вышла С исключением (откат), makedirs за её пределами не вызван
    assert conn.tx_committed is False
    makedirs_mock.assert_not_called()


@pytest.mark.asyncio
async def test_create_project_duplicate_name_no_transaction():
    """Дубликат имени → success=False, транзакция не начиналась."""
    conn = FakeConn()
    with patch("utils.projects.db.execute", new=AsyncMock()), \
         patch("utils.projects.db.fetchrow", new=AsyncMock(return_value={"project_id": 7})), \
         _patch_project_transaction(conn), \
         patch("utils.projects.os.makedirs"), \
         patch("utils.excel.create_user_dir", return_value="/tmp/u"):
        result = await projects.create_project(1, "Отпуск", template_key="vacation")

    assert result["success"] is False
    assert "уже существует" in result["message"].lower()
    assert conn.executed == []


@pytest.mark.asyncio
async def test_create_project_makedirs_error_after_commit_is_swallowed():
    """Ошибка ФС после коммита не валит создание (success=True, ошибка залогирована)."""
    conn = FakeConn(new_project_id=400)
    with patch("utils.projects.db.execute", new=AsyncMock()), \
         patch("utils.projects.db.fetchrow", new=AsyncMock(return_value=None)), \
         _patch_project_transaction(conn), \
         patch("utils.projects.os.makedirs", side_effect=OSError("disk full")), \
         patch("utils.excel.create_user_dir", return_value="/tmp/u"):
        result = await projects.create_project(1, "Поездка", template_key=None)

    assert result["success"] is True
    assert conn.tx_committed is True  # транзакция успешно закоммичена до ошибки ФС
