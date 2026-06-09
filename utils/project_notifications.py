"""
Repository слой для индивидуальных настроек уведомлений участника проекта.

Хранит, в каком режиме каждый участник хочет получать уведомления о новых
расходах проекта (feature_110). Отсутствие строки трактуется как режим 'all'
(обратная совместимость со старыми участниками).

Таблица: project_member_settings(project_id, user_id, expense_notify_mode,
                                 large_expense_threshold, updated_at)
"""

from decimal import Decimal
from typing import Optional

import config
from utils import db
from utils.logger import get_logger, log_error, log_event

logger = get_logger("utils.project_notifications")


def _default_settings(project_id: int, user_id) -> dict:
    """Настройки по умолчанию для участника без явной записи (режим ALL)."""
    return {
        "project_id": project_id,
        "user_id": str(user_id),
        "expense_notify_mode": config.ExpenseNotifyMode.DEFAULT,
        "large_expense_threshold": None,
        "updated_at": None,
    }


async def get_member_settings(project_id: int, user_id: int) -> dict:
    """
    Возвращает настройки уведомлений участника.

    Если строки нет — возвращает дефолт (режим 'all'), не создавая запись.
    Это гарантирует обратную совместимость: старые участники считаются ALL.
    """
    try:
        row = await db.fetchrow(
            """
            SELECT project_id, user_id, expense_notify_mode,
                   large_expense_threshold, updated_at
            FROM project_member_settings
            WHERE project_id = $1 AND user_id = $2
            """,
            project_id, str(user_id),
        )
        if not row:
            return _default_settings(project_id, user_id)
        return dict(row)
    except Exception as e:
        log_error(logger, e, "get_member_settings_error",
                  project_id=project_id, user_id=user_id)
        # При ошибке безопаснее вернуть дефолт (уведомлять), чем потерять уведомление
        return _default_settings(project_id, user_id)


async def set_notify_mode(
    project_id: int,
    user_id: int,
    mode: str,
    large_expense_threshold: Optional[Decimal] = None,
) -> bool:
    """
    Устанавливает режим уведомлений участника (upsert).

    Для режима LARGE_ONLY ожидается large_expense_threshold > 0.
    Для остальных режимов порог обнуляется.
    """
    if mode not in config.ExpenseNotifyMode.ALL_MODES:
        log_error(logger, ValueError(f"invalid mode: {mode}"),
                  "set_notify_mode_invalid_mode",
                  project_id=project_id, user_id=user_id, mode=mode)
        return False

    # Порог имеет смысл только для large_only
    if mode != config.ExpenseNotifyMode.LARGE_ONLY:
        large_expense_threshold = None

    threshold_val = (
        float(large_expense_threshold)
        if large_expense_threshold is not None else None
    )

    try:
        await db.execute(
            "INSERT INTO users(user_id) VALUES($1) ON CONFLICT (user_id) DO NOTHING",
            str(user_id),
        )
        await db.execute(
            """
            INSERT INTO project_member_settings
                (project_id, user_id, expense_notify_mode, large_expense_threshold, updated_at)
            VALUES ($1, $2, $3, $4, now())
            ON CONFLICT (project_id, user_id)
            DO UPDATE SET
                expense_notify_mode = EXCLUDED.expense_notify_mode,
                large_expense_threshold = EXCLUDED.large_expense_threshold,
                updated_at = now()
            """,
            project_id, str(user_id), mode, threshold_val,
        )
        log_event(logger, "project_member_notify_mode_set",
                  project_id=project_id, user_id=user_id, mode=mode,
                  has_threshold=threshold_val is not None)
        return True
    except Exception as e:
        log_error(logger, e, "set_notify_mode_error",
                  project_id=project_id, user_id=user_id, mode=mode)
        return False


def mode_display_name(mode: str) -> str:
    """Человекочитаемое название режима уведомлений."""
    names = {
        config.ExpenseNotifyMode.ALL: "Все расходы",
        config.ExpenseNotifyMode.LARGE_ONLY: "Только крупные",
        config.ExpenseNotifyMode.DISABLED: "Не уведомлять",
    }
    return names.get(mode, mode)
