"""
Утилиты для работы с данными расходов.
Изначально все хранилось в Excel, теперь вся логика чтения/записи переведена на Postgres.
Публичный API модуля (add_expense, get_month_expenses и т.п.) сохранён, но теперь функции асинхронные.
"""

import datetime
import os
import time
from typing import Optional

import pandas as pd

import config
from utils.logger import get_logger, log_error, log_event

from . import db

logger = get_logger("utils.excel")


def create_user_dir(user_id):
    """
    Директория для файлов пользователя (картинки, временные экспорты и т.п.).
    Оставляем файловую структуру, чтобы не ломать визуализацию/экспорт.
    """
    user_dir = os.path.join(config.DATA_DIR, str(user_id))
    if not os.path.exists(user_dir):
        os.makedirs(user_dir)
    return user_dir


# --- Вспомогательные функции для Postgres ---

def _normalize_project_id(project_id):
    """
    Для удобства сравнения в SQL: None -> None, иначе int.
    """
    if project_id is None:
        return None
    return int(project_id)


def _format_participant_label(participant_user_id) -> str:
    """
    Формат отображаемого имени участника в статистике проекта.
    В текущем UX для участников используется user_id.
    """
    if participant_user_id is None:
        return "Неизвестный участник"
    return f"ID: {participant_user_id}"


async def add_expense(user_id, amount, category_id, description: str = "", project_id=None):
    """
    Добавляет новый расход в БД.
    Если project_id указан, добавляет расход в проект.
    
    Permission required: ADD_EXPENSE (owner or editor for projects)
    
    Args:
        user_id: ID пользователя
        amount: Сумма расхода
        category_id: ID категории (int)
        description: Описание расхода
        project_id: ID проекта (опционально)
    """
    from utils import categories
    from utils.logger import get_logger, log_error, log_event
    from utils.permissions import Permission, has_permission

    expense_logger = get_logger("utils.excel")
    start_time = time.time()

    # Check permission for project expenses
    if project_id is not None:
        has_perm = await has_permission(user_id, project_id, Permission.ADD_EXPENSE)
        log_event(expense_logger, "add_expense_permission_check",
                 user_id=user_id, project_id=project_id, has_permission=has_perm)
        if not has_perm:
            log_error(expense_logger, Exception("Permission denied"),
                     "add_expense_permission_denied", user_id=user_id,
                     project_id=project_id)
            return False

    now = datetime.datetime.now()
    month = now.month
    date_val = now.date()
    time_val = now.time().replace(microsecond=0)
    project_id = _normalize_project_id(project_id)

    # Проверяем, что category_id - это число
    if isinstance(category_id, str):
        # Если передана строка (старый формат), пытаемся найти категорию по имени
        # Это для обратной совместимости
        try:
            category_id = int(category_id)
        except ValueError:
            # Если не число, ищем категорию по имени (legacy support)
            from utils import categories as cat_utils
            project_id_for_lookup = project_id
            cats = await cat_utils.get_categories_for_user_project(user_id, project_id_for_lookup)
            category_found = None
            for cat in cats:
                if cat['name'].lower() == category_id.lower():
                    category_found = cat
                    break
            if not category_found:
                # Пробуем глобальные категории
                cats_global = await cat_utils.get_categories_for_user_project(user_id, None)
                for cat in cats_global:
                    if cat['name'].lower() == category_id.lower():
                        category_found = cat
                        break
            if category_found:
                category_id = category_found['category_id']
            else:
                log_error(expense_logger, Exception(f"Category not found: {category_id}"),
                         "add_expense_category_not_found", user_id=user_id, category_name=category_id)
                return False

    category_id = int(category_id)

    log_event(expense_logger, "add_expense_start", user_id=user_id, project_id=project_id,
             amount=amount, category_id=category_id)

    try:
        # 1. Убедимся, что пользователь существует
        await db.execute(
            "INSERT INTO users(user_id) VALUES($1) ON CONFLICT (user_id) DO NOTHING",
            str(user_id),
        )

        # 2. Проверяем, что категория доступна для пользователя
        category = await categories.get_category_by_id(user_id, category_id)
        if not category and project_id is not None:
            # For shared projects, category may belong to another member (already permission-checked above)
            category = await categories.get_category_by_id_only(category_id)
        log_event(expense_logger, "add_expense_category_check",
                 user_id=user_id, category_id=category_id,
                 category_found=category is not None,
                 category_project_id=category['project_id'] if category else None)

        if not category:
            log_error(expense_logger, Exception("Category not found or access denied"),
                     "add_expense_category_invalid", user_id=user_id, category_id=category_id,
                     project_id=project_id)
            return False

        # Проверяем доступность категории для проекта
        if category['project_id'] is not None and category['project_id'] != project_id:
            log_error(expense_logger, Exception("Category not available for this project"),
                     "add_expense_category_project_mismatch", user_id=user_id,
                     category_id=category_id,
                     category_project_id=category['project_id'],
                     expense_project_id=project_id)
            return False

        # 3. Вставляем сам расход
        await db.execute(
            """
            INSERT INTO expenses(user_id, project_id, date, time, amount, category_id, description, month)
            VALUES($1, $2, $3, $4, $5, $6, $7, $8)
            """,
            str(user_id),
            project_id,
            date_val,
            time_val,
            float(amount),
            category_id,
            description or None,
            month,
        )

        duration = time.time() - start_time
        log_event(expense_logger, "add_expense_success", user_id=user_id, project_id=project_id,
                 amount=amount, category_id=category_id, duration=duration)
        return True
    except Exception as e:
        duration = time.time() - start_time
        log_error(expense_logger, e, "add_expense_error", user_id=user_id, project_id=project_id,
                 amount=amount, category_id=category_id, duration=duration)
        return False


# --- feature_110: создание расхода с возвратом id (для сервисного слоя) ---

# Базовое смещение для PostgreSQL advisory lock по проекту.
# Используется, чтобы сериализовать создание расходов в рамках одного проекта
# и закрыть гонку «два участника создают один и тот же расход одновременно».
_PROJECT_EXPENSE_LOCK_NAMESPACE = 110_000_000


async def create_expense(
    user_id,
    amount,
    category_id: int,
    description: str = "",
    project_id=None,
    *,
    conn=None,
) -> Optional[int]:
    """
    Создаёт расход и возвращает его id (в отличие от add_expense, который
    возвращает bool). Категория и права считаются уже проверенными вызывающим
    кодом (сервисным слоем). Подходит для использования внутри транзакции:
    передайте открытое соединение conn.

    Args:
        user_id: ID пользователя (автор расхода)
        amount: сумма
        category_id: ID категории (int)
        description: комментарий (опционально)
        project_id: ID проекта или None для личного расхода
        conn: открытое asyncpg-соединение/транзакция (опционально). Если не задано —
              используется общий пул через db.fetchval.

    Returns:
        id созданного расхода, либо None при ошибке.
    """
    now = datetime.datetime.now()
    project_id = _normalize_project_id(project_id)
    date_val = now.date()
    time_val = now.time().replace(microsecond=0)

    sql = """
        INSERT INTO expenses
            (user_id, project_id, date, time, amount, category_id, description, month,
             source_type, created_by_system, created_at)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, 'manual', FALSE, now())
        RETURNING id
    """
    params = (
        str(user_id), project_id, date_val, time_val,
        float(amount), int(category_id), description or None, now.month,
    )

    try:
        if conn is not None:
            expense_id = await conn.fetchval(sql, *params)
        else:
            expense_id = await db.fetchval(sql, *params)

        log_event(logger, "create_expense_success", user_id=user_id,
                  project_id=project_id, amount=amount, category_id=category_id,
                  expense_id=expense_id)
        return expense_id
    except Exception as e:
        log_error(logger, e, "create_expense_error", user_id=user_id,
                  project_id=project_id, amount=amount, category_id=category_id)
        return None


async def acquire_project_expense_lock(conn, project_id: int) -> None:
    """
    Берёт транзакционный advisory lock по проекту внутри транзакции conn.

    Lock автоматически освобождается при завершении транзакции. Сериализует
    одновременное создание расходов в одном проекте, чтобы проверка дубликата
    и вставка происходили атомарно относительно других участников.
    """
    await conn.execute(
        "SELECT pg_advisory_xact_lock($1)",
        _PROJECT_EXPENSE_LOCK_NAMESPACE + int(project_id),
    )


async def get_expense_by_id(expense_id: int, include_deleted: bool = False) -> Optional[dict]:
    """
    Возвращает расход по id вместе с именем категории.

    По умолчанию мягко удалённые расходы (deleted_at IS NOT NULL) не возвращаются —
    это нужно для корректной обработки ситуации «расход удалён до нажатия кнопки».
    """
    try:
        if include_deleted:
            row = await db.fetchrow(
                """
                SELECT e.id, e.user_id, e.project_id, e.date, e.time, e.amount,
                       e.category_id, e.description, e.month, e.created_at, e.deleted_at,
                       c.name AS category_name
                FROM expenses e
                JOIN categories c ON e.category_id = c.category_id
                WHERE e.id = $1
                """,
                expense_id,
            )
        else:
            row = await db.fetchrow(
                """
                SELECT e.id, e.user_id, e.project_id, e.date, e.time, e.amount,
                       e.category_id, e.description, e.month, e.created_at, e.deleted_at,
                       c.name AS category_name
                FROM expenses e
                JOIN categories c ON e.category_id = c.category_id
                WHERE e.id = $1 AND e.deleted_at IS NULL
                """,
                expense_id,
            )
        return dict(row) if row else None
    except Exception as e:
        log_error(logger, e, "get_expense_by_id_error", expense_id=expense_id)
        return None


async def soft_delete_expense(expense_id: int) -> bool:
    """
    Мягко удаляет расход (deleted_at = now()).

    Применяется только к ещё не удалённым расходам (idempotent: повторный вызов
    вернёт False). Сами данные сохраняются в БД.
    """
    try:
        result = await db.execute(
            "UPDATE expenses SET deleted_at = now() WHERE id = $1 AND deleted_at IS NULL",
            expense_id,
        )
        deleted = result != "UPDATE 0"
        if deleted:
            log_event(logger, "expense_soft_deleted", expense_id=expense_id)
        return deleted
    except Exception as e:
        log_error(logger, e, "soft_delete_expense_error", expense_id=expense_id)
        return False


async def get_month_expenses(user_id, month=None, year=None, project_id=None):
    """
    Returns expense statistics for the specified month.
    For projects: shows expenses from ALL project members.
    For personal (project_id=None): shows only user's own expenses.
    
    Permission required: VIEW_STATS (owner, editor, or viewer for projects)
    
    Args:
        user_id: ID of the requesting user (for access validation)
        month: Month number (1-12)
        year: Year (used for filtering by EXTRACT(YEAR FROM date))
        project_id: Project ID or None for personal expenses
    """
    if month is None:
        month = datetime.datetime.now().month
    if year is None:
        year = datetime.datetime.now().year
    project_id = _normalize_project_id(project_id)

    try:
        # If project_id is specified, validate user has permission
        if project_id is not None:
            from utils.permissions import Permission, has_permission
            if not await has_permission(user_id, project_id, Permission.VIEW_STATS):
                log_error(logger, Exception("Permission denied"),
                         "get_month_expenses_permission_denied", user_id=user_id, project_id=project_id)
                return {'total': 0, 'by_category': {}, 'by_participant': {}, 'count': 0}

        # For projects: get expenses from ALL members
        # For personal: get only user's expenses
        if project_id is not None:
            rows = await db.fetch(
                """
                SELECT e.amount, c.name as category, e.user_id
                FROM expenses e
                JOIN categories c ON e.category_id = c.category_id
                WHERE e.project_id = $1
                  AND e.month = $2
                  AND EXTRACT(YEAR FROM e.date) = $3
                """,
                project_id,
                month,
                year,
            )
        else:
            rows = await db.fetch(
                """
                SELECT e.amount, c.name as category
                FROM expenses e
                JOIN categories c ON e.category_id = c.category_id
                WHERE e.user_id = $1
                  AND e.month = $2
                  AND e.project_id IS NULL
                  AND EXTRACT(YEAR FROM e.date) = $3
                """,
                str(user_id),
                month,
                year,
            )
        if not rows:
                return {
                    "total": 0,
                    "by_category": {},
                    "by_participant": {},
                    "count": 0,
                }

        total = 0.0
        by_category = {}
        by_participant = {}
        for r in rows:
            amt = float(r["amount"])
            cat = r["category"]
            total += amt
            by_category[cat] = by_category.get(cat, 0.0) + amt
            if project_id is not None:
                participant_label = _format_participant_label(r.get("user_id"))
                by_participant[participant_label] = by_participant.get(participant_label, 0.0) + amt

        result = {
            "total": total,
            "by_category": by_category,
            "by_participant": by_participant,
            "count": len(rows),
        }
        log_event(logger, "get_month_expenses_success", user_id=user_id,
                 month=month, year=year, project_id=project_id,
                 total=total, count=len(rows), categories_count=len(by_category))
        return result
    except Exception as e:
        log_error(logger, e, "get_month_expenses_error", user_id=user_id,
                 month=month, year=year, project_id=project_id)
        return None


async def set_budget(user_id, amount, month=None, year=None, project_id=None):
    """
    Budget functionality disabled.
    Kept for backwards compatibility but does nothing.
    """
    log_event(logger, "set_budget_disabled", user_id=user_id,
             amount=amount, month=month, year=year, project_id=project_id)
    return True


async def get_category_expenses(user_id, category_id, year=None, project_id=None):
    """
    Returns expense statistics for a specific category over a year.
    For projects: shows expenses from ALL project members.
    For personal (project_id=None): shows only user's own expenses.
    
    Args:
        user_id: ID of the requesting user (for access validation)
        category_id: Category ID (int) or category name (str, for backwards compatibility)
        year: Year
        project_id: Project ID or None for personal expenses
    """
    from utils import categories

    if year is None:
        year = datetime.datetime.now().year
    project_id = _normalize_project_id(project_id)

    # Validate permission if project_id is specified
    if project_id is not None:
        from utils.permissions import Permission, has_permission
        if not await has_permission(user_id, project_id, Permission.VIEW_STATS):
            log_error(logger, Exception("Permission denied"),
                     "get_category_expenses_permission_denied", user_id=user_id, project_id=project_id)
            return None

    # If category_id is a string, find category by name
    if isinstance(category_id, str):
        cats = await categories.get_categories_for_user_project(user_id, project_id)
        category_found = None
        for cat in cats:
            if cat['name'].lower() == category_id.lower():
                category_found = cat
                break
        if not category_found:
            cats_global = await categories.get_categories_for_user_project(user_id, None)
            for cat in cats_global:
                if cat['name'].lower() == category_id.lower():
                    category_found = cat
                    break
        if category_found:
            category_id = category_found['category_id']
        else:
            log_error(logger, Exception(f"Category not found: {category_id}"),
                     "get_category_expenses_category_not_found", user_id=user_id, category_name=category_id)
            return None

    category_id = int(category_id)

    try:
        # For projects: get expenses from ALL members
        # For personal: get only user's expenses
        if project_id is not None:
            rows = await db.fetch(
                """
                SELECT amount, month
                FROM expenses
                WHERE category_id = $1
                  AND EXTRACT(YEAR FROM date) = $2
                  AND project_id = $3
                """,
                category_id,
                year,
                project_id,
            )
        else:
            rows = await db.fetch(
                """
                SELECT amount, month
                FROM expenses
                WHERE user_id = $1
                  AND category_id = $2
                  AND EXTRACT(YEAR FROM date) = $3
                  AND project_id IS NULL
                """,
                str(user_id),
                category_id,
                year,
            )
        if not rows:
            return {
                "total": 0,
                "by_month": {},
                "count": 0,
            }

        total = 0.0
        by_month = {}
        for r in rows:
            amt = float(r["amount"])
            m = int(r["month"])
            total += amt
            by_month[m] = by_month.get(m, 0.0) + amt

        result = {
            "total": total,
            "by_month": by_month,
            "count": len(rows),
        }
        log_event(logger, "get_category_expenses_success", user_id=user_id,
                 category_id=category_id, year=year, project_id=project_id,
                 total=total, count=len(rows))
        return result
    except Exception as e:
        log_error(logger, e, "get_category_expenses_error", user_id=user_id,
                 category_id=category_id, year=year, project_id=project_id)
        return None


async def get_all_expenses(user_id, year=None, project_id=None):
    """
    Returns all expenses for the specified year as a pandas.DataFrame.
    For projects: shows expenses from ALL project members.
    For personal (project_id=None): shows only user's own expenses.
    
    Args:
        user_id: ID of the requesting user (for access validation)
        year: Year
        project_id: Project ID or None for personal expenses
    """
    if year is None:
        year = datetime.datetime.now().year
    project_id = _normalize_project_id(project_id)

    try:
        # Validate permission if project_id is specified
        if project_id is not None:
            from utils.permissions import Permission, has_permission
            if not await has_permission(user_id, project_id, Permission.VIEW_HISTORY):
                log_error(logger, Exception("Permission denied"),
                         "get_all_expenses_permission_denied", user_id=user_id, project_id=project_id)
                return None

        # For projects: get expenses from ALL members
        # For personal: get only user's expenses
        if project_id is not None:
            rows = await db.fetch(
                """
                SELECT e.date, e.time, e.amount, c.name as category, e.description, 
                       e.month, e.project_id, e.user_id
                FROM expenses e
                JOIN categories c ON e.category_id = c.category_id
                WHERE e.project_id = $1
                  AND EXTRACT(YEAR FROM e.date) = $2
                ORDER BY e.date, e.time
                """,
                project_id,
                year,
            )
        else:
            rows = await db.fetch(
                """
                SELECT e.date, e.time, e.amount, c.name as category, e.description, 
                       e.month, e.project_id, e.user_id
                FROM expenses e
                JOIN categories c ON e.category_id = c.category_id
                WHERE e.user_id = $1
                  AND EXTRACT(YEAR FROM e.date) = $2
                  AND e.project_id IS NULL
                ORDER BY e.date, e.time
                """,
                str(user_id),
                year,
            )
        if not rows:
            log_event(logger, "get_all_expenses_empty", user_id=user_id,
                     year=year, project_id=project_id)
            return None

        data = [dict(r) for r in rows]
        result = pd.DataFrame(data)
        log_event(logger, "get_all_expenses_success", user_id=user_id,
                 year=year, project_id=project_id, rows_count=len(result))
        return result
    except Exception as e:
        log_error(logger, e, "get_all_expenses_error", user_id=user_id,
                 year=year, project_id=project_id)
        return None


async def get_day_expenses(user_id, date=None, project_id=None):
    """
    Returns expense statistics for the specified day.
    For projects: shows expenses from ALL project members.
    For personal (project_id=None): shows only user's own expenses.
    
    Args:
        user_id: ID of the requesting user (for access validation)
        date: Date string in 'YYYY-MM-DD' format
        project_id: Project ID or None for personal expenses
    """
    if date is None:
        date = datetime.datetime.now().strftime("%Y-%m-%d")

    project_id = _normalize_project_id(project_id)
    target_date = datetime.datetime.strptime(date, "%Y-%m-%d").date()

    try:
        # Validate permission if project_id is specified
        if project_id is not None:
            from utils.permissions import Permission, has_permission
            if not await has_permission(user_id, project_id, Permission.VIEW_STATS):
                log_error(logger, Exception("Permission denied"),
                         "get_day_expenses_permission_denied", user_id=user_id, project_id=project_id)
                return {'status': True, 'total': 0, 'by_category': {}, 'by_participant': {}, 'count': 0}

        # For projects: get expenses from ALL members
        # For personal: get only user's expenses
        if project_id is not None:
            rows = await db.fetch(
                """
                SELECT e.amount, c.name as category, e.user_id
                FROM expenses e
                JOIN categories c ON e.category_id = c.category_id
                WHERE e.project_id = $1
                  AND e.date = $2
                """,
                project_id,
                target_date,
            )
        else:
            rows = await db.fetch(
                """
                SELECT e.amount, c.name as category
                FROM expenses e
                JOIN categories c ON e.category_id = c.category_id
                WHERE e.user_id = $1
                  AND e.date = $2
                  AND e.project_id IS NULL
                """,
                str(user_id),
                target_date,
            )
        if not rows:
                return {
                    "status": True,
                    "total": 0,
                    "by_category": {},
                    "by_participant": {},
                    "count": 0,
                }

        total = 0.0
        by_category = {}
        by_participant = {}
        for r in rows:
            amt = float(r["amount"])
            cat = r["category"]
            total += amt
            by_category[cat] = by_category.get(cat, 0.0) + amt
            if project_id is not None:
                participant_label = _format_participant_label(r.get("user_id"))
                by_participant[participant_label] = by_participant.get(participant_label, 0.0) + amt

        result = {
            "status": True,
            "total": total,
            "by_category": by_category,
            "by_participant": by_participant,
            "count": len(rows),
        }
        log_event(logger, "get_day_expenses_success", user_id=user_id,
                 date=str(target_date), project_id=project_id,
                 total=total, count=len(rows))
        return result
    except Exception as e:
        log_error(logger, e, "get_day_expenses_error", user_id=user_id,
                 date=str(target_date), project_id=project_id)
        return None
