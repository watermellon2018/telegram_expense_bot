"""Утилиты для работы с постоянными доходами (recurring incomes)."""

import datetime
from typing import Optional

from utils import db
from utils.logger import get_logger, log_event, log_error
from utils import recurring as recurring_utils

logger = get_logger("utils.recurring_incomes")


async def create_rule(
    user_id: str,
    amount: float,
    income_category_id: int,
    comment: str,
    project_id: Optional[int],
    frequency_type: str,
    interval_value: Optional[int],
    weekday: Optional[int],
    day_of_month: Optional[int],
    is_last_day_of_month: bool,
    start_date: datetime.date,
) -> Optional[int]:
    """Создает правило постоянного дохода и при необходимости сразу добавляет запись дохода."""
    rule_proto = {
        "frequency_type": frequency_type,
        "interval_value": interval_value,
        "weekday": weekday,
        "day_of_month": day_of_month,
        "is_last_day_of_month": is_last_day_of_month,
    }
    now = datetime.datetime.utcnow()
    today = now.date()

    next_run_at = (
        recurring_utils.calculate_next_run(rule_proto, now)
        if start_date <= today
        else datetime.datetime.combine(start_date, datetime.time(0, 0, 0))
    )

    try:
        rule_id = await db.fetchval(
            """
            INSERT INTO recurring_incomes(
                user_id, amount, income_category_id, comment, project_id,
                frequency_type, interval_value, weekday, day_of_month,
                is_last_day_of_month, start_date, next_run_at
            )
            VALUES($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
            RETURNING id
            """,
            user_id,
            float(amount),
            int(income_category_id),
            comment or "",
            project_id,
            frequency_type,
            interval_value,
            weekday,
            day_of_month,
            is_last_day_of_month,
            start_date,
            next_run_at,
        )

        if start_date <= today:
            await db.execute(
                """
                INSERT INTO incomes(
                    user_id, amount, income_category_id, project_id,
                    description, month, income_date, recurring_income_id, created_by_system
                )
                VALUES($1, $2, $3, $4, $5, $6, $7, $8, TRUE)
                """,
                user_id,
                float(amount),
                int(income_category_id),
                project_id,
                comment or None,
                today.month,
                today,
                rule_id,
            )

        return rule_id
    except Exception as exc:
        log_error(logger, exc, "create_recurring_income_rule_error", user_id=user_id)
        return None


async def get_rules_for_user(user_id: str, project_id: Optional[int] = None) -> list:
    """Возвращает список правил постоянных доходов пользователя."""
    try:
        if project_id is None:
            rows = await db.fetch(
                """
                SELECT rr.*, c.name AS category_name
                FROM recurring_incomes rr
                JOIN income_categories c ON c.income_category_id = rr.income_category_id
                WHERE rr.user_id = $1
                  AND rr.project_id IS NULL
                ORDER BY
                    CASE WHEN rr.status = 'active' THEN 0 ELSE 1 END,
                    rr.amount DESC
                """,
                user_id,
            )
        else:
            rows = await db.fetch(
                """
                SELECT rr.*, c.name AS category_name
                FROM recurring_incomes rr
                JOIN income_categories c ON c.income_category_id = rr.income_category_id
                WHERE rr.user_id = $1
                  AND rr.project_id = $2
                ORDER BY
                    CASE WHEN rr.status = 'active' THEN 0 ELSE 1 END,
                    rr.amount DESC
                """,
                user_id,
                project_id,
            )
        return [dict(row) for row in rows]
    except Exception as exc:
        log_error(logger, exc, "get_recurring_income_rules_error", user_id=user_id)
        return []


async def get_rule_by_id(rule_id: int, user_id: str) -> Optional[dict]:
    """Возвращает правило по id с проверкой владельца."""
    try:
        row = await db.fetchrow(
            """
            SELECT rr.*, c.name AS category_name
            FROM recurring_incomes rr
            JOIN income_categories c ON c.income_category_id = rr.income_category_id
            WHERE rr.id = $1
              AND rr.user_id = $2
            """,
            rule_id,
            user_id,
        )
        return dict(row) if row else None
    except Exception as exc:
        log_error(logger, exc, "get_recurring_income_rule_error", rule_id=rule_id, user_id=user_id)
        return None


async def delete_rule(rule_id: int, user_id: str) -> bool:
    """Удаляет правило постоянного дохода."""
    try:
        result = await db.execute(
            "DELETE FROM recurring_incomes WHERE id = $1 AND user_id = $2",
            rule_id,
            user_id,
        )
        return result != "DELETE 0"
    except Exception as exc:
        log_error(logger, exc, "delete_recurring_income_rule_error", rule_id=rule_id, user_id=user_id)
        return False


async def pause_rule(rule_id: int, user_id: str) -> bool:
    """Ставит правило на паузу."""
    try:
        result = await db.execute(
            """
            UPDATE recurring_incomes
            SET status = 'paused', updated_at = NOW()
            WHERE id = $1
              AND user_id = $2
              AND status = 'active'
            """,
            rule_id,
            user_id,
        )
        return result != "UPDATE 0"
    except Exception as exc:
        log_error(logger, exc, "pause_recurring_income_rule_error", rule_id=rule_id, user_id=user_id)
        return False


async def resume_rule(rule_id: int, user_id: str) -> bool:
    """Возобновляет правило и пересчитывает next_run_at от текущего момента."""
    try:
        row = await db.fetchrow(
            "SELECT * FROM recurring_incomes WHERE id = $1 AND user_id = $2",
            rule_id,
            user_id,
        )
        if not row or row["status"] != "paused":
            return False

        now = datetime.datetime.utcnow()
        next_run = recurring_utils.calculate_next_run(dict(row), now)
        result = await db.execute(
            """
            UPDATE recurring_incomes
            SET status = 'active', next_run_at = $1, updated_at = NOW()
            WHERE id = $2
              AND user_id = $3
            """,
            next_run,
            rule_id,
            user_id,
        )
        return result != "UPDATE 0"
    except Exception as exc:
        log_error(logger, exc, "resume_recurring_income_rule_error", rule_id=rule_id, user_id=user_id)
        return False


async def process_recurring_incomes(bot) -> None:
    """Планировщик автогенерации фактических записей доходов по активным правилам."""
    now = datetime.datetime.utcnow()
    today = now.date()

    try:
        rules = await db.fetch(
            """
            SELECT rr.*, c.name AS category_name
            FROM recurring_incomes rr
            JOIN income_categories c ON c.income_category_id = rr.income_category_id
            WHERE rr.status = 'active'
              AND rr.next_run_at <= $1
            """,
            now,
        )
    except Exception as exc:
        log_error(logger, exc, "process_recurring_incomes_fetch_error")
        return

    for row in rules:
        rule = dict(row)
        rule_id = rule["id"]

        try:
            already_created = await db.fetchval(
                """
                SELECT 1
                FROM incomes
                WHERE recurring_income_id = $1
                  AND income_date = $2
                LIMIT 1
                """,
                rule_id,
                today,
            )
            if already_created:
                continue

            await db.execute(
                """
                INSERT INTO incomes(
                    user_id, amount, income_category_id, project_id,
                    description, month, income_date, recurring_income_id, created_by_system
                )
                VALUES($1, $2, $3, $4, $5, $6, $7, $8, TRUE)
                """,
                rule["user_id"],
                float(rule["amount"]),
                rule["income_category_id"],
                rule["project_id"],
                rule["comment"] or None,
                today.month,
                today,
                rule_id,
            )

            next_run = recurring_utils.calculate_next_run(rule, now)
            await db.execute(
                """
                UPDATE recurring_incomes
                SET next_run_at = $1,
                    updated_at = NOW()
                WHERE id = $2
                """,
                next_run,
                rule_id,
            )

            try:
                await bot.send_message(
                    chat_id=rule["user_id"],
                    text=(
                        "🔁 Добавлен постоянный доход:\n"
                        f"💰 {rule['amount']} — {rule['comment'] or rule.get('category_name', 'Доход')}"
                    ),
                )
            except Exception as notify_error:
                log_error(logger, notify_error, "process_recurring_incomes_notify_error", rule_id=rule_id)

            log_event(logger, "recurring_income_created", rule_id=rule_id, user_id=rule["user_id"])
        except Exception as exc:
            log_error(logger, exc, "process_recurring_income_rule_error", rule_id=rule_id)
