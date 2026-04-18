"""Утилиты для работы с доходами."""

import datetime
from typing import Optional, Dict

import pandas as pd

from utils import db
from utils.logger import get_logger, log_error, log_event
from utils import income_categories

logger = get_logger("utils.incomes")


def _normalize_project_id(project_id: Optional[int]) -> Optional[int]:
    if project_id is None:
        return None
    return int(project_id)


async def add_income(
    user_id: int,
    amount: float,
    income_category_id: int,
    description: str = "",
    project_id: Optional[int] = None,
    income_date: Optional[datetime.date] = None,
    recurring_income_id: Optional[int] = None,
    created_by_system: bool = False,
) -> bool:
    """Добавляет фактическую запись дохода."""
    try:
        project_id = _normalize_project_id(project_id)
        target_date = income_date or datetime.datetime.now().date()
        month = target_date.month

        if project_id is not None:
            from utils.permissions import Permission, has_permission
            if not await has_permission(user_id, project_id, Permission.ADD_EXPENSE):
                return False

        await db.execute(
            "INSERT INTO users(user_id) VALUES($1) ON CONFLICT (user_id) DO NOTHING",
            str(user_id),
        )

        category = await income_categories.get_income_category_by_id(user_id, int(income_category_id))
        if not category and project_id is not None:
            category = await income_categories.get_income_category_by_id_only(int(income_category_id))
        if not category:
            return False

        if category["project_id"] is not None and category["project_id"] != project_id:
            return False

        await db.execute(
            """
            INSERT INTO incomes(
                user_id,
                amount,
                income_category_id,
                project_id,
                description,
                month,
                income_date,
                recurring_income_id,
                created_by_system
            )
            VALUES($1, $2, $3, $4, $5, $6, $7, $8, $9)
            """,
            str(user_id),
            float(amount),
            int(income_category_id),
            project_id,
            description or None,
            month,
            target_date,
            recurring_income_id,
            created_by_system,
        )
        return True
    except Exception as exc:
        log_error(logger, exc, "add_income_error", user_id=user_id, project_id=project_id)
        return False


async def get_month_incomes(user_id: int, month: Optional[int] = None, year: Optional[int] = None, project_id: Optional[int] = None) -> Optional[Dict]:
    """Возвращает статистику доходов за месяц."""
    month = month or datetime.datetime.now().month
    year = year or datetime.datetime.now().year
    project_id = _normalize_project_id(project_id)

    try:
        if project_id is not None:
            from utils.permissions import Permission, has_permission
            if not await has_permission(user_id, project_id, Permission.VIEW_STATS):
                return {"total": 0.0, "by_category": {}, "count": 0}

            rows = await db.fetch(
                """
                SELECT i.amount, c.name AS category
                FROM incomes i
                JOIN income_categories c ON c.income_category_id = i.income_category_id
                WHERE i.project_id = $1
                  AND i.month = $2
                  AND EXTRACT(YEAR FROM i.income_date) = $3
                """,
                project_id,
                month,
                year,
            )
        else:
            rows = await db.fetch(
                """
                SELECT i.amount, c.name AS category
                FROM incomes i
                JOIN income_categories c ON c.income_category_id = i.income_category_id
                WHERE i.user_id = $1
                  AND i.project_id IS NULL
                  AND i.month = $2
                  AND EXTRACT(YEAR FROM i.income_date) = $3
                """,
                str(user_id),
                month,
                year,
            )

        if not rows:
            return {"total": 0.0, "by_category": {}, "count": 0}

        total = 0.0
        by_category: Dict[str, float] = {}
        for row in rows:
            amount = float(row["amount"])
            category = row["category"]
            total += amount
            by_category[category] = by_category.get(category, 0.0) + amount

        return {"total": total, "by_category": by_category, "count": len(rows)}
    except Exception as exc:
        log_error(logger, exc, "get_month_incomes_error", user_id=user_id, month=month, year=year, project_id=project_id)
        return None


async def get_day_incomes(user_id: int, date: Optional[str] = None, project_id: Optional[int] = None) -> Optional[Dict]:
    """Возвращает статистику доходов за день."""
    date = date or datetime.datetime.now().strftime("%Y-%m-%d")
    project_id = _normalize_project_id(project_id)
    target_date = datetime.datetime.strptime(date, "%Y-%m-%d").date()

    try:
        if project_id is not None:
            from utils.permissions import Permission, has_permission
            if not await has_permission(user_id, project_id, Permission.VIEW_STATS):
                return {"status": True, "total": 0.0, "by_category": {}, "count": 0}

            rows = await db.fetch(
                """
                SELECT i.amount, c.name AS category
                FROM incomes i
                JOIN income_categories c ON c.income_category_id = i.income_category_id
                WHERE i.project_id = $1
                  AND i.income_date = $2
                """,
                project_id,
                target_date,
            )
        else:
            rows = await db.fetch(
                """
                SELECT i.amount, c.name AS category
                FROM incomes i
                JOIN income_categories c ON c.income_category_id = i.income_category_id
                WHERE i.user_id = $1
                  AND i.project_id IS NULL
                  AND i.income_date = $2
                """,
                str(user_id),
                target_date,
            )

        if not rows:
            return {"status": True, "total": 0.0, "by_category": {}, "count": 0}

        total = 0.0
        by_category: Dict[str, float] = {}
        for row in rows:
            amount = float(row["amount"])
            category = row["category"]
            total += amount
            by_category[category] = by_category.get(category, 0.0) + amount

        return {"status": True, "total": total, "by_category": by_category, "count": len(rows)}
    except Exception as exc:
        log_error(logger, exc, "get_day_incomes_error", user_id=user_id, date=date, project_id=project_id)
        return None


async def get_all_incomes(user_id: int, year: Optional[int] = None, project_id: Optional[int] = None) -> Optional[pd.DataFrame]:
    """Возвращает все доходы за год в DataFrame."""
    year = year or datetime.datetime.now().year
    project_id = _normalize_project_id(project_id)

    try:
        if project_id is not None:
            from utils.permissions import Permission, has_permission
            if not await has_permission(user_id, project_id, Permission.VIEW_HISTORY):
                return None

            rows = await db.fetch(
                """
                SELECT i.income_date AS date,
                       i.amount,
                       c.name AS category,
                       i.description,
                       i.month,
                       i.project_id,
                       i.user_id,
                       i.created_at
                FROM incomes i
                JOIN income_categories c ON c.income_category_id = i.income_category_id
                WHERE i.project_id = $1
                  AND EXTRACT(YEAR FROM i.income_date) = $2
                ORDER BY i.income_date, i.created_at
                """,
                project_id,
                year,
            )
        else:
            rows = await db.fetch(
                """
                SELECT i.income_date AS date,
                       i.amount,
                       c.name AS category,
                       i.description,
                       i.month,
                       i.project_id,
                       i.user_id,
                       i.created_at
                FROM incomes i
                JOIN income_categories c ON c.income_category_id = i.income_category_id
                WHERE i.user_id = $1
                  AND i.project_id IS NULL
                  AND EXTRACT(YEAR FROM i.income_date) = $2
                ORDER BY i.income_date, i.created_at
                """,
                str(user_id),
                year,
            )

        if not rows:
            return None

        return pd.DataFrame([dict(row) for row in rows])
    except Exception as exc:
        log_error(logger, exc, "get_all_incomes_error", user_id=user_id, year=year, project_id=project_id)
        return None


async def get_yearly_income_by_category(user_id: int, year: Optional[int] = None, project_id: Optional[int] = None) -> Dict[str, float]:
    """Возвращает агрегат доходов по категориям за год."""
    df = await get_all_incomes(user_id, year, project_id)
    if df is None or df.empty:
        return {}

    df["amount"] = df["amount"].astype(float)
    grouped = df.groupby("category")["amount"].sum()
    return {str(category): float(amount) for category, amount in grouped.items()}


async def get_yearly_income_vs_expense(
    user_id: int,
    year: Optional[int] = None,
    project_id: Optional[int] = None,
) -> Dict[str, Dict[int, float]]:
    """Возвращает помесячные агрегаты доходов и расходов за год."""
    year = year or datetime.datetime.now().year
    project_id = _normalize_project_id(project_id)

    income_rows = await db.fetch(
        """
        SELECT month, SUM(amount) AS total
        FROM incomes
        WHERE (($1::int IS NULL AND user_id = $2 AND project_id IS NULL) OR project_id = $1)
          AND EXTRACT(YEAR FROM income_date) = $3
        GROUP BY month
        """,
        project_id,
        str(user_id),
        year,
    )

    expense_rows = await db.fetch(
        """
        SELECT month, SUM(amount) AS total
        FROM expenses
        WHERE (($1::int IS NULL AND user_id = $2 AND project_id IS NULL) OR project_id = $1)
          AND EXTRACT(YEAR FROM date) = $3
        GROUP BY month
        """,
        project_id,
        str(user_id),
        year,
    )

    incomes_by_month = {int(row["month"]): float(row["total"]) for row in income_rows}
    expenses_by_month = {int(row["month"]): float(row["total"]) for row in expense_rows}

    log_event(logger, "yearly_income_vs_expense", user_id=user_id, year=year, project_id=project_id)
    return {
        "incomes": incomes_by_month,
        "expenses": expenses_by_month,
    }
