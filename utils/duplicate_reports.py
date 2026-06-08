"""
Repository слой для отметок «возможный дубликат» расхода (feature_110).

Таблица: expense_duplicate_reports(id, expense_id, reported_by_user_id, status,
                                   created_at, resolved_at, resolved_by_user_id)

Ограничение UNIQUE(expense_id, reported_by_user_id) гарантирует, что один
пользователь не отметит один расход дважды.
"""

from typing import Optional

import asyncpg

import config
from utils import db
from utils.logger import get_logger, log_error, log_event

logger = get_logger("utils.duplicate_reports")


async def create_report(expense_id: int, reported_by_user_id: int) -> Optional[int]:
    """
    Создаёт отметку «возможный дубликат».

    Идемпотентно по (expense_id, reported_by_user_id): при повторной отметке
    тем же пользователем возвращает None (повторная отметка не создаётся).
    Использует ON CONFLICT DO NOTHING + RETURNING — гонка двух одновременных
    отметок одним пользователем безопасна.

    Возвращает:
        id новой отметки, либо None если такая отметка уже была (или ошибка).
    """
    try:
        report_id = await db.fetchval(
            """
            INSERT INTO expense_duplicate_reports
                (expense_id, reported_by_user_id, status, created_at)
            VALUES ($1, $2, $3, now())
            ON CONFLICT (expense_id, reported_by_user_id) DO NOTHING
            RETURNING id
            """,
            expense_id, str(reported_by_user_id), config.DuplicateReportStatus.OPEN,
        )
        if report_id is None:
            log_event(logger, "duplicate_report_already_exists",
                      expense_id=expense_id, reported_by_user_id=reported_by_user_id)
            return None

        log_event(logger, "duplicate_report_created",
                  report_id=report_id, expense_id=expense_id,
                  reported_by_user_id=reported_by_user_id)
        return report_id
    except asyncpg.ForeignKeyViolationError:
        # Расход был удалён до создания отметки — обрабатываем мягко
        log_event(logger, "duplicate_report_expense_missing",
                  expense_id=expense_id, reported_by_user_id=reported_by_user_id)
        return None
    except Exception as e:
        log_error(logger, e, "create_report_error",
                  expense_id=expense_id, reported_by_user_id=reported_by_user_id)
        return None


async def get_report_by_id(report_id: int) -> Optional[dict]:
    """Возвращает отметку по id (или None)."""
    try:
        row = await db.fetchrow(
            """
            SELECT id, expense_id, reported_by_user_id, status,
                   created_at, resolved_at, resolved_by_user_id
            FROM expense_duplicate_reports
            WHERE id = $1
            """,
            report_id,
        )
        return dict(row) if row else None
    except Exception as e:
        log_error(logger, e, "get_report_by_id_error", report_id=report_id)
        return None


async def has_open_report(expense_id: int, reported_by_user_id: int) -> bool:
    """Проверяет, есть ли уже отметка этого пользователя по этому расходу."""
    try:
        exists = await db.fetchval(
            """
            SELECT 1 FROM expense_duplicate_reports
            WHERE expense_id = $1 AND reported_by_user_id = $2
            LIMIT 1
            """,
            expense_id, str(reported_by_user_id),
        )
        return exists is not None
    except Exception as e:
        log_error(logger, e, "has_open_report_error",
                  expense_id=expense_id, reported_by_user_id=reported_by_user_id)
        return False


async def resolve_report(
    report_id: int,
    resolved_by_user_id: int,
    status: str,
) -> bool:
    """
    Помечает отметку как рассмотренную (kept или deleted).

    Обновляет только отметки в статусе 'open' — повторное разрешение игнорируется
    (защита от двойного нажатия). Возвращает True при успешном обновлении.
    """
    if status not in (config.DuplicateReportStatus.KEPT,
                      config.DuplicateReportStatus.DELETED):
        log_error(logger, ValueError(f"invalid resolve status: {status}"),
                  "resolve_report_invalid_status", report_id=report_id, status=status)
        return False

    try:
        result = await db.execute(
            """
            UPDATE expense_duplicate_reports
            SET status = $1, resolved_at = now(), resolved_by_user_id = $2
            WHERE id = $3 AND status = $4
            """,
            status, str(resolved_by_user_id), report_id,
            config.DuplicateReportStatus.OPEN,
        )
        updated = result != "UPDATE 0"
        if updated:
            log_event(logger, "duplicate_report_resolved",
                      report_id=report_id, status=status,
                      resolved_by_user_id=resolved_by_user_id)
        return updated
    except Exception as e:
        log_error(logger, e, "resolve_report_error",
                  report_id=report_id, status=status)
        return False
