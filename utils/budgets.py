"""
CRUD-операции для работы с бюджетами.
Поддерживает как личные бюджеты (project_id=None), так и бюджеты проектов.
"""

import datetime
from typing import Optional
from . import db
from utils.logger import get_logger, log_event, log_error

logger = get_logger("utils.budgets")


def _normalize_project_id(project_id) -> Optional[int]:
    if project_id is None:
        return None
    return int(project_id)


def _row_to_dict(row) -> dict:
    return {
        'id':                     row['id'],
        'user_id':                row['user_id'],
        'project_id':             row['project_id'],
        'amount':                 float(row['amount']),
        'month':                  row['month'],
        'year':                   row['year'],
        'notify_enabled':         row['notify_enabled'],
        'notify_threshold':       float(row['notify_threshold']) if row['notify_threshold'] else None,
        'last_notified_spending': float(row['last_notified_spending']) if row['last_notified_spending'] else None,
        'threshold_notified_at':  row['threshold_notified_at'],
        'overspent_notified_at':  row['overspent_notified_at'],
        'created_at':             row['created_at'],
        'updated_at':             row['updated_at'],
    }


async def get_budget(user_id: int, month: int, year: int,
                     project_id=None) -> Optional[dict]:
    """
    Получить бюджет за конкретный месяц/год.
    Возвращает None если бюджет не установлен.
    """
    project_id = _normalize_project_id(project_id)
    try:
        if project_id is None:
            row = await db.fetchrow(
                """
                SELECT * FROM budgets
                WHERE user_id = $1 AND month = $2 AND year = $3
                  AND project_id IS NULL
                """,
                str(user_id), month, year
            )
        else:
            row = await db.fetchrow(
                """
                SELECT * FROM budgets
                WHERE user_id = $1 AND month = $2 AND year = $3
                  AND project_id = $4
                """,
                str(user_id), month, year, project_id
            )
        if row is None:
            return None
        return _row_to_dict(row)
    except Exception as e:
        log_error(logger, e, "get_budget_error",
                  user_id=user_id, month=month, year=year, project_id=project_id)
        return None


async def get_or_inherit_budget(user_id: int, month: int, year: int,
                                project_id=None) -> Optional[dict]:
    """
    Получить бюджет за месяц.
    Если бюджет на текущий месяц не установлен — вернуть самый свежий из прошлых.
    Реализует требование: «если пользователь не установил, берётся с прошлого месяца».
    """
    budget = await get_budget(user_id, month, year, project_id)
    if budget is not None:
        return budget

    project_id = _normalize_project_id(project_id)
    try:
        if project_id is None:
            row = await db.fetchrow(
                """
                SELECT * FROM budgets
                WHERE user_id = $1 AND project_id IS NULL
                  AND (year < $3 OR (year = $3 AND month < $2))
                ORDER BY year DESC, month DESC
                LIMIT 1
                """,
                str(user_id), month, year
            )
        else:
            row = await db.fetchrow(
                """
                SELECT * FROM budgets
                WHERE user_id = $1 AND project_id = $4
                  AND (year < $3 OR (year = $3 AND month < $2))
                ORDER BY year DESC, month DESC
                LIMIT 1
                """,
                str(user_id), month, year, project_id
            )
        if row is None:
            return None
        return _row_to_dict(row)
    except Exception as e:
        log_error(logger, e, "get_or_inherit_budget_error",
                  user_id=user_id, month=month, year=year, project_id=project_id)
        return None


async def set_budget(user_id: int, month: int, year: int, amount: float,
                     project_id=None) -> Optional[dict]:
    """
    Установить или обновить бюджет на месяц (UPSERT).
    При изменении суммы сбрасывает счётчики уведомлений.
    """
    project_id = _normalize_project_id(project_id)
    try:
        if project_id is None:
            row = await db.fetchrow(
                """
                INSERT INTO budgets (user_id, project_id, amount, month, year, updated_at)
                VALUES ($1, NULL, $2, $3, $4, now())
                ON CONFLICT (user_id, month, year) WHERE project_id IS NULL
                DO UPDATE SET
                    amount                  = EXCLUDED.amount,
                    updated_at              = now(),
                    -- Reset notifications when budget amount changes
                    threshold_notified_at   = CASE WHEN budgets.amount != EXCLUDED.amount
                                                   THEN NULL ELSE budgets.threshold_notified_at END,
                    overspent_notified_at   = CASE WHEN budgets.amount != EXCLUDED.amount
                                                   THEN NULL ELSE budgets.overspent_notified_at END,
                    last_notified_spending  = CASE WHEN budgets.amount != EXCLUDED.amount
                                                   THEN NULL ELSE budgets.last_notified_spending END
                RETURNING *
                """,
                str(user_id), amount, month, year
            )
        else:
            row = await db.fetchrow(
                """
                INSERT INTO budgets (user_id, project_id, amount, month, year, updated_at)
                VALUES ($1, $5, $2, $3, $4, now())
                ON CONFLICT (user_id, project_id, month, year) WHERE project_id IS NOT NULL
                DO UPDATE SET
                    amount                  = EXCLUDED.amount,
                    updated_at              = now(),
                    threshold_notified_at   = CASE WHEN budgets.amount != EXCLUDED.amount
                                                   THEN NULL ELSE budgets.threshold_notified_at END,
                    overspent_notified_at   = CASE WHEN budgets.amount != EXCLUDED.amount
                                                   THEN NULL ELSE budgets.overspent_notified_at END,
                    last_notified_spending  = CASE WHEN budgets.amount != EXCLUDED.amount
                                                   THEN NULL ELSE budgets.last_notified_spending END
                RETURNING *
                """,
                str(user_id), amount, month, year, project_id
            )
        log_event(logger, "set_budget_success",
                  user_id=user_id, month=month, year=year, amount=amount, project_id=project_id)
        return _row_to_dict(row) if row else None
    except Exception as e:
        log_error(logger, e, "set_budget_error",
                  user_id=user_id, month=month, year=year, amount=amount, project_id=project_id)
        return None


async def set_notification(user_id: int, month: int, year: int, threshold: float,
                           project_id=None) -> Optional[dict]:
    """
    Включить уведомления и установить порог.
    Бюджет на этот месяц должен уже существовать.
    """
    project_id = _normalize_project_id(project_id)
    try:
        if project_id is None:
            row = await db.fetchrow(
                """
                UPDATE budgets
                SET notify_enabled = TRUE,
                    notify_threshold = $2,
                    threshold_notified_at = NULL,
                    overspent_notified_at = NULL,
                    last_notified_spending = NULL,
                    updated_at = now()
                WHERE user_id = $1 AND month = $3 AND year = $4
                  AND project_id IS NULL
                RETURNING *
                """,
                str(user_id), threshold, month, year
            )
        else:
            row = await db.fetchrow(
                """
                UPDATE budgets
                SET notify_enabled = TRUE,
                    notify_threshold = $2,
                    threshold_notified_at = NULL,
                    overspent_notified_at = NULL,
                    last_notified_spending = NULL,
                    updated_at = now()
                WHERE user_id = $1 AND month = $3 AND year = $4
                  AND project_id = $5
                RETURNING *
                """,
                str(user_id), threshold, month, year, project_id
            )
        log_event(logger, "set_notification_success",
                  user_id=user_id, month=month, year=year, threshold=threshold)
        return _row_to_dict(row) if row else None
    except Exception as e:
        log_error(logger, e, "set_notification_error",
                  user_id=user_id, month=month, year=year)
        return None


async def disable_notification(user_id: int, month: int, year: int,
                               project_id=None) -> Optional[dict]:
    """
    Отключить уведомления для бюджета.
    """
    project_id = _normalize_project_id(project_id)
    try:
        if project_id is None:
            row = await db.fetchrow(
                """
                UPDATE budgets
                SET notify_enabled = FALSE, updated_at = now()
                WHERE user_id = $1 AND month = $2 AND year = $3
                  AND project_id IS NULL
                RETURNING *
                """,
                str(user_id), month, year
            )
        else:
            row = await db.fetchrow(
                """
                UPDATE budgets
                SET notify_enabled = FALSE, updated_at = now()
                WHERE user_id = $1 AND month = $2 AND year = $3
                  AND project_id = $4
                RETURNING *
                """,
                str(user_id), month, year, project_id
            )
        log_event(logger, "disable_notification_success", user_id=user_id, month=month, year=year)
        return _row_to_dict(row) if row else None
    except Exception as e:
        log_error(logger, e, "disable_notification_error",
                  user_id=user_id, month=month, year=year)
        return None


async def get_all_active_budgets_with_notifications(month: int, year: int) -> list[dict]:
    """
    Получить все бюджеты с включёнными уведомлениями за текущий месяц.
    Используется планировщиком проверки порогов.
    """
    try:
        rows = await db.fetch(
            """
            SELECT * FROM budgets
            WHERE notify_enabled = TRUE AND month = $1 AND year = $2
            ORDER BY id
            """,
            month, year
        )
        return [_row_to_dict(r) for r in rows]
    except Exception as e:
        log_error(logger, e, "get_active_budgets_error", month=month, year=year)
        return []


async def update_notification_state(budget_id: int,
                                    threshold_notified_at=None,
                                    overspent_notified_at=None,
                                    last_notified_spending=None) -> None:
    """
    Обновить поля состояния уведомлений после отправки.
    Передавать только те поля, которые изменились.
    """
    try:
        fields = ["updated_at = now()"]
        params: list = [budget_id]
        idx = 2

        if threshold_notified_at is not None:
            fields.append(f"threshold_notified_at = ${idx}")
            params.append(threshold_notified_at)
            idx += 1

        if overspent_notified_at is not None:
            fields.append(f"overspent_notified_at = ${idx}")
            params.append(overspent_notified_at)
            idx += 1

        if last_notified_spending is not None:
            fields.append(f"last_notified_spending = ${idx}")
            params.append(last_notified_spending)

        await db.execute(
            f"UPDATE budgets SET {', '.join(fields)} WHERE id = $1",
            *params
        )
    except Exception as e:
        log_error(logger, e, "update_notification_state_error", budget_id=budget_id)


async def get_budgets_for_year(user_id: int, year: int,
                               project_id=None) -> list[dict]:
    """
    Получить все бюджеты за год (для графика сравнения).
    Возвращает список, отсортированный по месяцу.
    """
    project_id = _normalize_project_id(project_id)
    try:
        if project_id is None:
            rows = await db.fetch(
                """
                SELECT * FROM budgets
                WHERE user_id = $1 AND year = $2 AND project_id IS NULL
                ORDER BY month ASC
                """,
                str(user_id), year
            )
        else:
            rows = await db.fetch(
                """
                SELECT * FROM budgets
                WHERE user_id = $1 AND year = $2 AND project_id = $3
                ORDER BY month ASC
                """,
                str(user_id), year, project_id
            )
        return [_row_to_dict(r) for r in rows]
    except Exception as e:
        log_error(logger, e, "get_budgets_for_year_error",
                  user_id=user_id, year=year, project_id=project_id)
        return []
