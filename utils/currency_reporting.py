"""Separate historical untyped amounts from converted reporting totals."""

import datetime
from decimal import Decimal

import pandas as pd

from utils import db
from utils.permissions import Permission, require_permission


def _filters(user_id, project_id, *, year=None, month=None, date=None,
             category_id=None, start_date=None, end_date=None):
    params = [str(user_id)] if project_id is None else [int(project_id)]
    clauses = ["e.user_id = $1 AND e.project_id IS NULL" if project_id is None
               else "e.project_id = $1"]
    for expression, value in (("EXTRACT(YEAR FROM e.date)", year),
                              ("EXTRACT(MONTH FROM e.date)", month),
                              ("e.date", datetime.date.fromisoformat(date) if isinstance(date, str) else date),
                              ("e.category_id", category_id)):
        if value is not None:
            params.append(value)
            clauses.append(f"{expression} = ${len(params)}")
    for operator, value in ((">=", start_date), ("<=", end_date)):
        if value is not None:
            params.append(value)
            clauses.append(f"e.date {operator} ${len(params)}")
    return clauses, params


async def get_legacy_summary(user_id, project_id=None, **period) -> dict:
    """Return original untyped totals, never combined with reporting amounts."""
    await require_permission(user_id, project_id, Permission.VIEW_STATS)
    result = {}
    for table in ("expenses", "incomes"):
        if table == "incomes" and period.get("category_id") is not None:
            result[table] = {"count": 0, "total": Decimal(0)}
            continue
        clauses, params = _filters(user_id, project_id, **period)
        if table == "incomes":
            clauses = [clause.replace("e.date", "e.income_date") for clause in clauses]
        clauses.append("e.currency IS NULL")
        if table == "expenses":
            clauses.append("e.deleted_at IS NULL")
        row = await db.fetchrow(
            f"SELECT COUNT(*) AS count, COALESCE(SUM(e.amount), 0) AS total "
            f"FROM {table} e WHERE {' AND '.join(clauses)}", *params)
        result[table] = dict(row) if row else {"count": 0, "total": Decimal(0)}
    return result


def format_legacy_summary(summary: dict) -> str:
    lines = []
    for key, label in (("expenses", "Расходы"), ("incomes", "Доходы")):
        item = summary.get(key, {})
        if item.get("count", 0):
            lines.append(f"{label}: {item['count']} записей; исходная сумма {item['total']:,.2f}")
    if not lines:
        return ""
    return ("Исторические записи без валюты (отдельно от итогов):\n"
            + "\n".join(lines)
            + "\nЭти суммы не пересчитаны: валюта записей неизвестна.")


def format_project_totals(stats: dict) -> str:
    from utils.currencies import format_money
    text = f"Расходов с валютой: {stats['count']}\nСумма: {format_money(stats['total'], stats.get('currency'))}"
    legacy = format_legacy_summary(stats.get('legacy', {}))
    return text + ("\n\n" + legacy if legacy else "")


async def get_export_expenses(user_id, project_id=None, *, year=None, month=None) -> pd.DataFrame:
    """Export original amounts and immutable FX metadata, including legacy rows."""
    await require_permission(user_id, project_id, Permission.VIEW_HISTORY)
    clauses, params = _filters(user_id, project_id, year=year, month=month)
    clauses.append("e.deleted_at IS NULL")
    rows = await db.fetch(
        "SELECT e.id, e.user_id, e.date, e.month, c.name AS category, "
        "e.description, e.amount AS original_amount, e.currency, "
        "e.reporting_currency, e.reporting_amount AS amount, "
        "e.fx_rate, e.fx_date, e.fx_source "
        "FROM expenses e LEFT JOIN categories c ON c.category_id = e.category_id "
        f"WHERE {' AND '.join(clauses)} ORDER BY e.date, e.id", *params)
    frame = pd.DataFrame([dict(row) for row in rows])
    for column in ('original_amount', 'amount', 'fx_rate'):
        if column in frame.columns:
            frame[column] = pd.to_numeric(frame[column], errors='raise')
    return frame
