"""
Утилиты для работы с данными расходов.
Изначально все хранилось в Excel, теперь вся логика чтения/записи переведена на Postgres.
Публичный API модуля (add_expense, get_month_expenses и т.п.) сохранён, но теперь функции асинхронные.
"""

import os
import datetime
import pandas as pd
import time

import config
from . import db
from utils.logger import get_logger, log_event, log_error

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
    import time
    from utils.logger import get_logger, log_event, log_error
    from utils import categories
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


async def get_month_expenses(user_id, month=None, year=None, project_id=None):
    """
    Returns expense statistics for the specified month.
    For projects: shows expenses from ALL project members.
    For personal (project_id=None): shows only user's own expenses.
    
    Permission required: VIEW_STATS (owner, editor, or viewer for projects)
    
    Args:
        user_id: ID of the requesting user (for access validation)
        month: Month number (1-12)
        year: Year (currently not used in filtering, but kept for API compatibility)
        project_id: Project ID or None for personal expenses
    """
    if month is None:
        month = datetime.datetime.now().month
    project_id = _normalize_project_id(project_id)

    try:
        # If project_id is specified, validate user has permission
        if project_id is not None:
            from utils.permissions import Permission, has_permission
            if not await has_permission(user_id, project_id, Permission.VIEW_STATS):
                log_error(logger, Exception("Permission denied"), 
                         "get_month_expenses_permission_denied", user_id=user_id, project_id=project_id)
                return {'total': 0, 'by_category': {}, 'count': 0}
        
        # For projects: get expenses from ALL members
        # For personal: get only user's expenses
        if project_id is not None:
            rows = await db.fetch(
                """
                SELECT e.amount, c.name as category
                FROM expenses e
                JOIN categories c ON e.category_id = c.category_id
                WHERE e.project_id = $1
                  AND e.month = $2
                """,
                project_id,
                month,
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
                """,
                str(user_id),
                month,
            )
        if not rows:
            return {
                "total": 0,
                "by_category": {},
                "count": 0,
            }

        total = 0.0
        by_category = {}
        for r in rows:
            amt = float(r["amount"])
            cat = r["category"]
            total += amt
            by_category[cat] = by_category.get(cat, 0.0) + amt

        result = {
            "total": total,
            "by_category": by_category,
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
                return {'status': True, 'total': 0, 'by_category': {}, 'count': 0}
        
        # For projects: get expenses from ALL members
        # For personal: get only user's expenses
        if project_id is not None:
            rows = await db.fetch(
                """
                SELECT e.amount, c.name as category
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
                "count": 0,
            }

        total = 0.0
        by_category = {}
        for r in rows:
            amt = float(r["amount"])
            cat = r["category"]
            total += amt
            by_category[cat] = by_category.get(cat, 0.0) + amt

        result = {
            "status": True,
            "total": total,
            "by_category": by_category,
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
