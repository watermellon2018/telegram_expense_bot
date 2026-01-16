"""
Утилиты для работы с данными расходов.
Изначально все хранилось в Excel, теперь вся логика чтения/записи переведена на Postgres.
Публичный API модуля (add_expense, get_month_expenses и т.п.) сохранён, но теперь функции асинхронные.
"""

import os
import datetime
import pandas as pd
import logging

import config
from . import db

logger = logging.getLogger(__name__)


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


async def add_expense(user_id, amount, category, description: str = "", project_id=None):
    """
    Добавляет новый расход в БД.
    Если project_id указан, добавляет расход в проект.
    """
    now = datetime.datetime.now()
    month = now.month
    date_val = now.date()
    time_val = now.time().replace(microsecond=0)
    category = category.lower()
    project_id = _normalize_project_id(project_id)

    try:
        # 1. Убедимся, что пользователь существует
        await db.execute(
            "INSERT INTO users(user_id) VALUES($1) ON CONFLICT (user_id) DO NOTHING",
            str(user_id),
        )

        # 2. Вставляем сам расход
        await db.execute(
            """
            INSERT INTO expenses(user_id, project_id, date, time, amount, category, description, month)
            VALUES($1, $2, $3, $4, $5, $6, $7, $8)
            """,
            str(user_id),
            project_id,
            date_val,
            time_val,
            float(amount),
            category,
            description or None,
            month,
        )

        # 3. Обновляем таблицу budget (как раньше обновляли лист Budget.actual)
        # Сначала гарантируем, что строка для месяца существует
        await db.execute(
            """
            INSERT INTO budget(user_id, project_id, month, budget, actual)
            VALUES($1, $2, $3, 0, 0)
            ON CONFLICT (user_id, project_id, month) DO NOTHING
            """,
            str(user_id),
            project_id,
            month,
        )

        # Затем пересчитываем actual как сумму по expenses
        await db.execute(
            """
            UPDATE budget b
            SET actual = COALESCE((
                SELECT SUM(e.amount)
                FROM expenses e
                WHERE e.user_id = b.user_id
                  AND ((e.project_id IS NULL AND b.project_id IS NULL) OR e.project_id = b.project_id)
                  AND e.month = b.month
            ), 0)
            WHERE b.user_id = $1
              AND ((b.project_id IS NULL AND $2::int IS NULL) OR b.project_id = $2::int)
              AND b.month = $3
            """,
            str(user_id),
            project_id,
            month,
        )
        return True
    except Exception as e:
        logger.error(f"Ошибка при добавлении расхода в БД: {e}")
        return False


async def get_month_expenses(user_id, month=None, year=None, project_id=None):
    """
    Возвращает статистику расходов за указанный месяц.
    """
    if month is None:
        month = datetime.datetime.now().month
    project_id = _normalize_project_id(project_id)

    try:
        rows = await db.fetch(
            """
            SELECT amount, category
            FROM expenses
            WHERE user_id = $1
              AND month = $2
              AND ((project_id IS NULL AND $3::int IS NULL) OR project_id = $3::int)
            """,
            str(user_id),
            month,
            project_id,
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

        return {
            "total": total,
            "by_category": by_category,
            "count": len(rows),
        }
    except Exception as e:
        logger.error(f"Ошибка при получении статистики за месяц из БД: {e}")
        return None


async def set_budget(user_id, amount, month=None, year=None, project_id=None):
    """
    Устанавливает бюджет на указанный месяц.
    """
    if month is None:
        month = datetime.datetime.now().month
    project_id = _normalize_project_id(project_id)

    try:
        await db.execute(
            """
            INSERT INTO budget(user_id, project_id, month, budget, actual)
            VALUES($1, $2, $3, $4, 0)
            ON CONFLICT (user_id, project_id, month)
            DO UPDATE SET budget = EXCLUDED.budget
            """,
            str(user_id),
            project_id,
            month,
            float(amount),
        )
        return True
    except Exception as e:
        logger.error(f"Ошибка при установке бюджета в БД: {e}")
        return False


async def get_category_expenses(user_id, category, year=None, project_id=None):
    """
    Возвращает статистику расходов по указанной категории за год.
    """
    if year is None:
        year = datetime.datetime.now().year
    project_id = _normalize_project_id(project_id)
    category = category.lower()

    try:
        rows = await db.fetch(
            """
            SELECT amount, month
            FROM expenses
            WHERE user_id = $1
              AND category = $2
              AND EXTRACT(YEAR FROM date) = $3
              AND ((project_id IS NULL AND $4::int IS NULL) OR project_id = $4::int)
            """,
            str(user_id),
            category,
            year,
            project_id,
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

        return {
            "total": total,
            "by_month": by_month,
            "count": len(rows),
        }
    except Exception as e:
        logger.error(f"Ошибка при получении статистики по категории из БД: {e}")
        return None


async def get_all_expenses(user_id, year=None, project_id=None):
    """
    Возвращает все расходы за указанный год в виде pandas.DataFrame.
    """
    if year is None:
        year = datetime.datetime.now().year
    project_id = _normalize_project_id(project_id)

    try:
        rows = await db.fetch(
            """
            SELECT date, time, amount, category, description, month, project_id
            FROM expenses
            WHERE user_id = $1
              AND EXTRACT(YEAR FROM date) = $2
              AND ((project_id IS NULL AND $3::int IS NULL) OR project_id = $3::int)
            ORDER BY date, time
            """,
            str(user_id),
            year,
            project_id,
        )
        if not rows:
            return None

        data = [dict(r) for r in rows]
        return pd.DataFrame(data)
    except Exception as e:
        logger.error(f"Ошибка при получении всех расходов из БД: {e}")
        return None


async def get_day_expenses(user_id, date=None, project_id=None):
    """
    Возвращает статистику расходов за указанный день.
    """
    if date is None:
        date = datetime.datetime.now().strftime("%Y-%m-%d")

    project_id = _normalize_project_id(project_id)
    target_date = datetime.datetime.strptime(date, "%Y-%m-%d").date()

    try:
        rows = await db.fetch(
            """
            SELECT amount, category
            FROM expenses
            WHERE user_id = $1
              AND date = $2
              AND ((project_id IS NULL AND $3::int IS NULL) OR project_id = $3::int)
            """,
            str(user_id),
            target_date,
            project_id,
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

        return {
            "status": True,
            "total": total,
            "by_category": by_category,
            "count": len(rows),
        }
    except Exception as e:
        logger.error(f"Error getting daily statistics from DB: {e}")
        return None
