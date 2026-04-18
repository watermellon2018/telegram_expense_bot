"""
Утилиты для работы с категориями доходов.
Поддерживает пользовательские и системные категории, глобальные и привязанные к проектам.
"""

import re
from typing import Optional, List, Dict

from . import db
from utils.logger import get_logger, log_event, log_error

logger = get_logger("utils.income_categories")


def normalize_category_name(name: str) -> str:
    """Нормализует имя категории для сравнения: trim + collapse spaces + lower."""
    collapsed = re.sub(r"\s+", " ", (name or "").strip())
    return collapsed.lower()


def sanitize_category_name(name: str) -> str:
    """Возвращает чистое отображаемое имя категории без лишних пробелов."""
    return re.sub(r"\s+", " ", (name or "").strip())


async def get_income_categories_for_user_project(user_id: int, project_id: Optional[int] = None) -> List[Dict]:
    """
    Возвращает активные категории доходов для пользователя и проекта.

    Для shared проекта: категории проекта + глобальные категории владельца проекта.
    Для личного режима: только глобальные категории пользователя.
    """
    try:
        if project_id is not None:
            from utils.permissions import Permission, has_permission
            if not await has_permission(user_id, project_id, Permission.VIEW_STATS):
                return []

            rows = await db.fetch(
                """
                WITH deduplicated AS (
                    SELECT DISTINCT ON (LOWER(REGEXP_REPLACE(BTRIM(c.name), '\\s+', ' ', 'g')))
                           c.income_category_id, c.name, c.is_system, c.is_active,
                           c.project_id, c.created_at, c.user_id
                    FROM income_categories c
                    WHERE c.is_active = TRUE
                      AND (
                        c.project_id = $1
                        OR (
                            c.project_id IS NULL
                            AND c.user_id = (SELECT user_id FROM projects WHERE project_id = $1)
                        )
                      )
                    ORDER BY LOWER(REGEXP_REPLACE(BTRIM(c.name), '\\s+', ' ', 'g')),
                             CASE WHEN c.project_id = $1 THEN 0 ELSE 1 END,
                             c.is_system DESC
                )
                SELECT * FROM deduplicated
                ORDER BY is_system DESC, name ASC
                """,
                project_id,
            )
        else:
            rows = await db.fetch(
                """
                SELECT income_category_id, name, is_system, is_active, project_id, created_at, user_id
                FROM income_categories
                WHERE user_id = $1
                  AND project_id IS NULL
                  AND is_active = TRUE
                ORDER BY is_system DESC, name ASC
                """,
                str(user_id),
            )

        return [
            {
                "income_category_id": row["income_category_id"],
                "name": row["name"],
                "is_system": row["is_system"],
                "is_active": row["is_active"],
                "project_id": row["project_id"],
                "created_at": row["created_at"].isoformat() if row["created_at"] else None,
            }
            for row in rows
        ]
    except Exception as exc:
        log_error(logger, exc, "get_income_categories_error", user_id=user_id, project_id=project_id)
        return []


async def get_income_category_by_name(
    user_id: int,
    name: str,
    project_id: Optional[int] = None,
) -> Optional[Dict]:
    """Возвращает активную категорию дохода по нормализованному имени."""
    try:
        normalized = normalize_category_name(name)
        if project_id is not None:
            row = await db.fetchrow(
                """
                SELECT income_category_id, name, is_system, is_active, project_id, created_at
                FROM income_categories
                WHERE LOWER(REGEXP_REPLACE(BTRIM(name), '\\s+', ' ', 'g')) = $1
                  AND is_active = TRUE
                  AND (
                    project_id = $2
                    OR (
                        project_id IS NULL
                        AND user_id = (SELECT user_id FROM projects WHERE project_id = $2)
                    )
                  )
                ORDER BY CASE WHEN project_id = $2 THEN 0 ELSE 1 END
                LIMIT 1
                """,
                normalized,
                project_id,
            )
        else:
            row = await db.fetchrow(
                """
                SELECT income_category_id, name, is_system, is_active, project_id, created_at
                FROM income_categories
                WHERE user_id = $1
                  AND project_id IS NULL
                  AND is_active = TRUE
                  AND LOWER(REGEXP_REPLACE(BTRIM(name), '\\s+', ' ', 'g')) = $2
                LIMIT 1
                """,
                str(user_id),
                normalized,
            )

        if not row:
            return None

        return {
            "income_category_id": row["income_category_id"],
            "name": row["name"],
            "is_system": row["is_system"],
            "is_active": row["is_active"],
            "project_id": row["project_id"],
            "created_at": row["created_at"].isoformat() if row["created_at"] else None,
        }
    except Exception as exc:
        log_error(logger, exc, "get_income_category_by_name_error", user_id=user_id, name=name)
        return None


async def get_income_category_by_id(user_id: int, income_category_id: int) -> Optional[Dict]:
    """Получает категорию дохода по ID с проверкой доступа пользователя."""
    try:
        row = await db.fetchrow(
            """
            SELECT c.income_category_id, c.name, c.is_system, c.is_active, c.project_id, c.created_at
            FROM income_categories c
            WHERE c.income_category_id = $1
              AND c.is_active = TRUE
              AND (
                  c.user_id = $2
                  OR EXISTS (
                      SELECT 1
                      FROM projects p
                      LEFT JOIN project_members pm
                        ON pm.project_id = p.project_id AND pm.user_id = $2
                      WHERE p.project_id = c.project_id
                        AND p.deleted_at IS NULL
                        AND (p.user_id = $2 OR pm.user_id = $2)
                  )
              )
            """,
            income_category_id,
            str(user_id),
        )
        if not row:
            return None

        return {
            "income_category_id": row["income_category_id"],
            "name": row["name"],
            "is_system": row["is_system"],
            "is_active": row["is_active"],
            "project_id": row["project_id"],
            "created_at": row["created_at"].isoformat() if row["created_at"] else None,
        }
    except Exception as exc:
        log_error(logger, exc, "get_income_category_by_id_error", user_id=user_id, income_category_id=income_category_id)
        return None


async def get_income_category_by_id_only(income_category_id: int) -> Optional[Dict]:
    """Получает активную категорию дохода по ID без проверки владельца."""
    try:
        row = await db.fetchrow(
            """
            SELECT income_category_id, name, is_system, is_active, project_id, created_at
            FROM income_categories
            WHERE income_category_id = $1
              AND is_active = TRUE
            """,
            income_category_id,
        )
        if not row:
            return None
        return {
            "income_category_id": row["income_category_id"],
            "name": row["name"],
            "is_system": row["is_system"],
            "is_active": row["is_active"],
            "project_id": row["project_id"],
            "created_at": row["created_at"].isoformat() if row["created_at"] else None,
        }
    except Exception as exc:
        log_error(logger, exc, "get_income_category_by_id_only_error", income_category_id=income_category_id)
        return None


async def create_income_category(
    user_id: int,
    name: str,
    project_id: Optional[int] = None,
    is_system: bool = False,
) -> Dict:
    """
    Создает или реактивирует категорию дохода.

    Правила:
    - активный дубликат => ошибка
    - неактивный дубликат => реактивация
    - сравнение по нормализованному имени
    """
    try:
        clean_name = sanitize_category_name(name)
        normalized = normalize_category_name(name)
        if not clean_name:
            return {"success": False, "message": "Название категории не может быть пустым"}

        if project_id is not None:
            from utils.permissions import Permission, has_permission
            if not await has_permission(user_id, project_id, Permission.ADD_CATEGORY):
                return {"success": False, "message": "У вас нет прав на создание категорий доходов в этом проекте"}

        await db.execute(
            "INSERT INTO users(user_id) VALUES($1) ON CONFLICT (user_id) DO NOTHING",
            str(user_id),
        )

        existing_active = await db.fetchrow(
            """
            SELECT income_category_id, name
            FROM income_categories
            WHERE user_id = $1
              AND ((project_id IS NULL AND $2::int IS NULL) OR project_id = $2)
              AND is_active = TRUE
              AND LOWER(REGEXP_REPLACE(BTRIM(name), '\\s+', ' ', 'g')) = $3
            LIMIT 1
            """,
            str(user_id),
            project_id,
            normalized,
        )
        if existing_active:
            return {
                "success": False,
                "message": f"Категория '{existing_active['name']}' уже существует",
            }

        existing_inactive = await db.fetchrow(
            """
            SELECT income_category_id
            FROM income_categories
            WHERE user_id = $1
              AND ((project_id IS NULL AND $2::int IS NULL) OR project_id = $2)
              AND is_active = FALSE
              AND LOWER(REGEXP_REPLACE(BTRIM(name), '\\s+', ' ', 'g')) = $3
            LIMIT 1
            """,
            str(user_id),
            project_id,
            normalized,
        )

        if existing_inactive:
            income_category_id = existing_inactive["income_category_id"]
            await db.execute(
                """
                UPDATE income_categories
                SET is_active = TRUE,
                    is_system = $1,
                    name = $2
                WHERE income_category_id = $3
                  AND user_id = $4
                """,
                is_system,
                clean_name,
                income_category_id,
                str(user_id),
            )
            return {
                "success": True,
                "income_category_id": income_category_id,
                "name": clean_name,
                "project_id": project_id,
                "message": f"Категория '{clean_name}' восстановлена",
            }

        income_category_id = await db.fetchval(
            """
            INSERT INTO income_categories(user_id, project_id, name, is_system, is_active, created_at)
            VALUES($1, $2, $3, $4, TRUE, CURRENT_TIMESTAMP)
            RETURNING income_category_id
            """,
            str(user_id),
            project_id,
            clean_name,
            is_system,
        )

        return {
            "success": True,
            "income_category_id": income_category_id,
            "name": clean_name,
            "project_id": project_id,
            "message": f"Категория '{clean_name}' создана",
        }
    except Exception as exc:
        log_error(logger, exc, "create_income_category_error", user_id=user_id, name=name, project_id=project_id)
        return {"success": False, "message": f"Ошибка при создании категории дохода: {exc}"}


async def deactivate_income_category(user_id: int, income_category_id: int) -> Dict:
    """
    Деактивирует категорию дохода.

    Блокирует деактивацию, если категория используется активными recurring income правилами.
    """
    try:
        category = await get_income_category_by_id(user_id, income_category_id)
        if not category:
            return {"success": False, "message": "Категория дохода не найдена"}

        if category["project_id"] is not None:
            from utils.permissions import Permission, has_permission
            if not await has_permission(user_id, category["project_id"], Permission.DELETE_CATEGORY):
                return {"success": False, "message": "У вас нет прав на деактивацию категорий доходов в этом проекте"}

        recurring_usage_count = await db.fetchval(
            """
            SELECT COUNT(*)
            FROM recurring_incomes
            WHERE income_category_id = $1
              AND status = 'active'
            """,
            income_category_id,
        )
        if recurring_usage_count and recurring_usage_count > 0:
            return {
                "success": False,
                "message": (
                    "Эта категория используется в активных правилах постоянного дохода. "
                    "Сначала удалите или измените эти правила в разделе 'Постоянный доход'."
                ),
            }

        await db.execute(
            """
            UPDATE income_categories
            SET is_active = FALSE
            WHERE income_category_id = $1
              AND user_id = $2
            """,
            income_category_id,
            str(user_id),
        )

        log_event(logger, "income_category_deactivated", user_id=user_id, income_category_id=income_category_id)
        return {"success": True, "message": f"Категория '{category['name']}' деактивирована"}
    except Exception as exc:
        log_error(logger, exc, "deactivate_income_category_error", user_id=user_id, income_category_id=income_category_id)
        return {"success": False, "message": f"Ошибка при деактивации категории дохода: {exc}"}


async def ensure_system_income_categories_exist(user_id: int) -> None:
    """Гарантирует наличие системных категорий доходов у пользователя."""
    import config

    try:
        await db.execute(
            "INSERT INTO users(user_id) VALUES($1) ON CONFLICT (user_id) DO NOTHING",
            str(user_id),
        )

        for category_name in config.DEFAULT_INCOME_CATEGORIES.keys():
            await create_income_category(
                user_id=user_id,
                name=category_name,
                project_id=None,
                is_system=True,
            )

        log_event(logger, "ensure_system_income_categories_success", user_id=user_id)
    except Exception as exc:
        log_error(logger, exc, "ensure_system_income_categories_error", user_id=user_id)
