"""
MVP-утилиты для теоретического кэшбэка.

Важно:
- рассчитывается только теоретический кэшбэк;
- соответствие идет по названию категории расхода;
- итог может отличаться от фактического начисления банка.
"""

import datetime
from typing import Dict, List, Optional, Tuple

from utils import db
from utils.logger import get_logger, log_event, log_error

logger = get_logger("utils.cashback")

POTENTIAL_CASHBACK_DISCLAIMER = (
    "Теоретический кэшбэк рассчитан по категории расхода и может отличаться от "
    "фактического начисления банка."
)

DEFAULT_GLOBAL_CASHBACK_CATEGORIES = [
    "продукты",
    "рестораны",
    "транспорт",
    "такси",
    "маркетплейсы",
    "аптека",
    "развлечения",
]

DEFAULT_CASHBACK_CATEGORY_EMOJIS = {
    "продукты": "🍎",
    "рестораны": "🍽️",
    "транспорт": "🚌",
    "такси": "🚕",
    "маркетплейсы": "🛒",
    "аптека": "💊",
    "развлечения": "🎭",
}


def _normalize_name(name: str) -> str:
    return " ".join((name or "").strip().lower().split())


def _fmt_amount(value: float) -> str:
    return f"{value:,.2f}".replace(",", " ")


def get_cashback_category_emoji(category_name: str) -> str:
    normalized = _normalize_name(category_name)
    if normalized in DEFAULT_CASHBACK_CATEGORY_EMOJIS:
        return DEFAULT_CASHBACK_CATEGORY_EMOJIS[normalized]

    try:
        import config

        return config.DEFAULT_CATEGORIES.get(normalized, "📦")
    except Exception:
        return "📦"


async def _ensure_user_exists(user_id: int) -> None:
    await db.execute(
        "INSERT INTO users(user_id) VALUES($1) ON CONFLICT (user_id) DO NOTHING",
        str(user_id),
    )


async def ensure_global_cashback_categories_exist() -> None:
    """Идемпотентно гарантирует наличие базовых глобальных cashback-категорий."""
    try:
        for cat_name in DEFAULT_GLOBAL_CASHBACK_CATEGORIES:
            await db.execute(
                """
                INSERT INTO cashback_categories(name, is_global, user_id, created_at)
                VALUES($1, TRUE, NULL, NOW())
                ON CONFLICT DO NOTHING
                """,
                cat_name,
            )
    except Exception as e:
        log_error(logger, e, "ensure_global_cashback_categories_error")


# ---------------------------------------------------------------------------
# Cards
# ---------------------------------------------------------------------------

async def list_user_cards(user_id: int, include_inactive: bool = False) -> List[Dict]:
    try:
        rows = await db.fetch(
            """
            SELECT id, card_name, is_active, created_at, updated_at
            FROM user_cards
            WHERE user_id = $1
              AND ($2::boolean = TRUE OR is_active = TRUE)
            ORDER BY is_active DESC, created_at ASC
            """,
            str(user_id),
            include_inactive,
        )
        return [
            {
                "id": r["id"],
                "card_name": r["card_name"],
                "is_active": r["is_active"],
                "created_at": r["created_at"],
                "updated_at": r["updated_at"],
            }
            for r in rows
        ]
    except Exception as e:
        log_error(logger, e, "list_user_cards_error", user_id=user_id)
        return []


async def create_user_card(user_id: int, card_name: str) -> Dict:
    card_name = " ".join(card_name.strip().split())
    if not card_name:
        return {"success": False, "message": "Название карты не может быть пустым."}

    try:
        await _ensure_user_exists(user_id)

        existing = await db.fetchrow(
            """
            SELECT id
            FROM user_cards
            WHERE user_id = $1
              AND LOWER(REGEXP_REPLACE(BTRIM(card_name), '\\s+', ' ', 'g'))
                  = LOWER(REGEXP_REPLACE(BTRIM($2), '\\s+', ' ', 'g'))
              AND is_active = TRUE
            """,
            str(user_id),
            card_name,
        )
        if existing:
            return {"success": False, "message": "Такая активная карта уже существует."}

        card_id = await db.fetchval(
            """
            INSERT INTO user_cards(user_id, card_name, is_active, created_at, updated_at)
            VALUES($1, $2, TRUE, NOW(), NOW())
            RETURNING id
            """,
            str(user_id),
            card_name,
        )
        log_event(logger, "cashback_card_created", user_id=user_id, card_id=card_id)
        return {"success": True, "card_id": card_id, "card_name": card_name}
    except Exception as e:
        log_error(logger, e, "create_user_card_error", user_id=user_id, card_name=card_name)
        return {"success": False, "message": "Не удалось создать карту."}


async def edit_user_card(user_id: int, card_id: int, new_card_name: str) -> Dict:
    new_card_name = " ".join(new_card_name.strip().split())
    if not new_card_name:
        return {"success": False, "message": "Новое название карты не может быть пустым."}

    try:
        existing = await db.fetchrow(
            """
            SELECT id
            FROM user_cards
            WHERE id = $1 AND user_id = $2
            """,
            card_id,
            str(user_id),
        )
        if not existing:
            return {"success": False, "message": "Карта не найдена."}

        duplicate = await db.fetchrow(
            """
            SELECT id
            FROM user_cards
            WHERE user_id = $1
              AND id <> $2
              AND is_active = TRUE
              AND LOWER(REGEXP_REPLACE(BTRIM(card_name), '\\s+', ' ', 'g'))
                  = LOWER(REGEXP_REPLACE(BTRIM($3), '\\s+', ' ', 'g'))
            """,
            str(user_id),
            card_id,
            new_card_name,
        )
        if duplicate:
            return {"success": False, "message": "Карта с таким названием уже существует."}

        await db.execute(
            """
            UPDATE user_cards
            SET card_name = $1, updated_at = NOW()
            WHERE id = $2 AND user_id = $3
            """,
            new_card_name,
            card_id,
            str(user_id),
        )
        log_event(logger, "cashback_card_updated", user_id=user_id, card_id=card_id)
        return {"success": True, "card_id": card_id, "card_name": new_card_name}
    except Exception as e:
        log_error(logger, e, "edit_user_card_error", user_id=user_id, card_id=card_id)
        return {"success": False, "message": "Не удалось обновить карту."}


async def deactivate_user_card(user_id: int, card_id: int) -> Dict:
    try:
        row = await db.fetchrow(
            """
            UPDATE user_cards
            SET is_active = FALSE, updated_at = NOW()
            WHERE id = $1 AND user_id = $2 AND is_active = TRUE
            RETURNING id, card_name
            """,
            card_id,
            str(user_id),
        )
        if not row:
            return {"success": False, "message": "Активная карта не найдена."}
        log_event(logger, "cashback_card_deactivated", user_id=user_id, card_id=card_id)
        return {"success": True, "card_id": row["id"], "card_name": row["card_name"]}
    except Exception as e:
        log_error(logger, e, "deactivate_user_card_error", user_id=user_id, card_id=card_id)
        return {"success": False, "message": "Не удалось деактивировать карту."}


async def activate_user_card(user_id: int, card_id: int) -> Dict:
    try:
        card = await db.fetchrow(
            """
            SELECT id, card_name, is_active
            FROM user_cards
            WHERE id = $1 AND user_id = $2
            """,
            card_id,
            str(user_id),
        )
        if not card:
            return {"success": False, "message": "Карта не найдена."}
        if card["is_active"]:
            return {"success": False, "message": "Карта уже активна."}

        duplicate = await db.fetchrow(
            """
            SELECT id
            FROM user_cards
            WHERE user_id = $1
              AND is_active = TRUE
              AND id <> $2
              AND LOWER(REGEXP_REPLACE(BTRIM(card_name), '\\s+', ' ', 'g'))
                  = LOWER(REGEXP_REPLACE(BTRIM($3), '\\s+', ' ', 'g'))
            """,
            str(user_id),
            card_id,
            card["card_name"],
        )
        if duplicate:
            return {
                "success": False,
                "message": "Есть активная карта с таким же названием. Переименуйте одну из карт.",
            }

        row = await db.fetchrow(
            """
            UPDATE user_cards
            SET is_active = TRUE, updated_at = NOW()
            WHERE id = $1 AND user_id = $2
            RETURNING id, card_name
            """,
            card_id,
            str(user_id),
        )
        if not row:
            return {"success": False, "message": "Карта не найдена."}

        log_event(logger, "cashback_card_activated", user_id=user_id, card_id=card_id)
        return {"success": True, "card_id": row["id"], "card_name": row["card_name"]}
    except Exception as e:
        log_error(logger, e, "activate_user_card_error", user_id=user_id, card_id=card_id)
        return {"success": False, "message": "Не удалось активировать карту."}


async def hard_delete_user_card(user_id: int, card_id: int) -> Dict:
    try:
        card = await db.fetchrow(
            """
            SELECT id, card_name
            FROM user_cards
            WHERE id = $1 AND user_id = $2
            """,
            card_id,
            str(user_id),
        )
        if not card:
            return {"success": False, "message": "Карта не найдена."}

        rules_count = await db.fetchval(
            """
            SELECT COUNT(*)
            FROM user_cashback_rules
            WHERE user_id = $1
              AND user_card_id = $2
            """,
            str(user_id),
            card_id,
        )
        if rules_count and int(rules_count) > 0:
            return {
                "success": False,
                "message": "По карте есть правила кэшбека. Сначала удалите связанные правила.",
            }

        row = await db.fetchrow(
            """
            DELETE FROM user_cards
            WHERE id = $1 AND user_id = $2
            RETURNING id, card_name
            """,
            card_id,
            str(user_id),
        )
        if not row:
            return {"success": False, "message": "Карта не найдена."}

        log_event(logger, "cashback_card_hard_deleted", user_id=user_id, card_id=card_id)
        return {"success": True, "card_id": row["id"], "card_name": row["card_name"]}
    except Exception as e:
        log_error(logger, e, "hard_delete_user_card_error", user_id=user_id, card_id=card_id)
        return {"success": False, "message": "Не удалось удалить карту."}


# ---------------------------------------------------------------------------
# Cashback categories
# ---------------------------------------------------------------------------

async def list_cashback_categories(user_id: int) -> List[Dict]:
    try:
        await ensure_global_cashback_categories_exist()
        rows = await db.fetch(
            """
            SELECT id, name, is_global, user_id, created_at
            FROM cashback_categories
            WHERE is_global = TRUE
               OR (is_global = FALSE AND user_id = $1)
            ORDER BY is_global DESC, name ASC
            """,
            str(user_id),
        )
        return [
            {
                "id": r["id"],
                "name": r["name"],
                "is_global": r["is_global"],
                "user_id": r["user_id"],
                "created_at": r["created_at"],
            }
            for r in rows
        ]
    except Exception as e:
        log_error(logger, e, "list_cashback_categories_error", user_id=user_id)
        return []


async def create_custom_cashback_category(user_id: int, name: str) -> Dict:
    category_name = " ".join(name.strip().split())
    if not category_name:
        return {"success": False, "message": "Название категории не может быть пустым."}

    try:
        await _ensure_user_exists(user_id)
        await ensure_global_cashback_categories_exist()

        duplicate = await db.fetchrow(
            """
            SELECT id
            FROM cashback_categories
            WHERE is_global = FALSE
              AND user_id = $1
              AND LOWER(REGEXP_REPLACE(BTRIM(name), '\\s+', ' ', 'g'))
                  = LOWER(REGEXP_REPLACE(BTRIM($2), '\\s+', ' ', 'g'))
            """,
            str(user_id),
            category_name,
        )
        if duplicate:
            return {"success": False, "message": "Такая пользовательская категория уже существует."}

        category_id = await db.fetchval(
            """
            INSERT INTO cashback_categories(name, is_global, user_id, created_at)
            VALUES($1, FALSE, $2, NOW())
            RETURNING id
            """,
            category_name,
            str(user_id),
        )
        log_event(logger, "cashback_category_created", user_id=user_id, category_id=category_id)
        return {"success": True, "category_id": category_id, "name": category_name}
    except Exception as e:
        log_error(
            logger,
            e,
            "create_custom_cashback_category_error",
            user_id=user_id,
            name=category_name,
        )
        return {"success": False, "message": "Не удалось создать категорию кэшбэка."}


async def delete_custom_cashback_category(user_id: int, category_id: int) -> Dict:
    try:
        category = await db.fetchrow(
            """
            SELECT id, name
            FROM cashback_categories
            WHERE id = $1
              AND user_id = $2
              AND is_global = FALSE
            """,
            category_id,
            str(user_id),
        )
        if not category:
            return {
                "success": False,
                "message": "Пользовательская категория не найдена.",
            }

        usage_count = await db.fetchval(
            """
            SELECT COUNT(*)
            FROM user_cashback_rules
            WHERE user_id = $1
              AND cashback_category_id = $2
            """,
            str(user_id),
            category_id,
        )
        if usage_count and int(usage_count) > 0:
            return {
                "success": False,
                "message": (
                    "Категория используется в правилах кэшбэка. "
                    "Сначала удалите связанные правила."
                ),
            }

        await db.execute(
            """
            DELETE FROM cashback_categories
            WHERE id = $1
              AND user_id = $2
              AND is_global = FALSE
            """,
            category_id,
            str(user_id),
        )
        log_event(
            logger,
            "cashback_category_deleted",
            user_id=user_id,
            category_id=category_id,
        )
        return {
            "success": True,
            "category_id": category_id,
            "name": category["name"],
        }
    except Exception as e:
        log_error(
            logger,
            e,
            "delete_custom_cashback_category_error",
            user_id=user_id,
            category_id=category_id,
        )
        return {"success": False, "message": "Не удалось удалить категорию кэшбэка."}


async def _get_cashback_category_for_user(user_id: int, category_id: int) -> Optional[Dict]:
    row = await db.fetchrow(
        """
        SELECT id, name, is_global, user_id
        FROM cashback_categories
        WHERE id = $1
          AND (is_global = TRUE OR user_id = $2)
        """,
        category_id,
        str(user_id),
    )
    if not row:
        return None
    return dict(row)


# ---------------------------------------------------------------------------
# Cashback rules
# ---------------------------------------------------------------------------

async def list_user_cashback_rules(user_id: int, year: int, month: int) -> List[Dict]:
    try:
        rows = await db.fetch(
            """
            SELECT
                r.id,
                r.user_card_id,
                uc.card_name,
                r.cashback_category_id,
                cc.name AS cashback_category_name,
                r.year,
                r.month,
                r.percent,
                r.created_at,
                r.updated_at
            FROM user_cashback_rules r
            JOIN user_cards uc ON uc.id = r.user_card_id
            JOIN cashback_categories cc ON cc.id = r.cashback_category_id
            WHERE r.user_id = $1
              AND r.year = $2
              AND r.month = $3
            ORDER BY r.percent DESC, cc.name ASC
            """,
            str(user_id),
            year,
            month,
        )
        return [dict(r) for r in rows]
    except Exception as e:
        log_error(
            logger,
            e,
            "list_user_cashback_rules_error",
            user_id=user_id,
            year=year,
            month=month,
        )
        return []


async def create_user_cashback_rule(
    user_id: int,
    user_card_id: int,
    cashback_category_id: int,
    year: int,
    month: int,
    percent: float,
) -> Dict:
    if percent < 0 or percent > 100:
        return {"success": False, "message": "Процент должен быть в диапазоне от 0 до 100."}

    try:
        await _ensure_user_exists(user_id)

        card = await db.fetchrow(
            """
            SELECT id, card_name, is_active
            FROM user_cards
            WHERE id = $1 AND user_id = $2
            """,
            user_card_id,
            str(user_id),
        )
        if not card:
            return {"success": False, "message": "Карта не найдена."}
        if not card["is_active"]:
            return {"success": False, "message": "Правила можно создавать только для активной карты."}

        category = await _get_cashback_category_for_user(user_id, cashback_category_id)
        if not category:
            return {"success": False, "message": "Категория кэшбэка не найдена."}

        existing = await db.fetchrow(
            """
            SELECT id
            FROM user_cashback_rules
            WHERE user_card_id = $1
              AND cashback_category_id = $2
              AND year = $3
              AND month = $4
            """,
            user_card_id,
            cashback_category_id,
            year,
            month,
        )
        if existing:
            return {
                "success": False,
                "message": (
                    "Для этой карты и категории уже есть правило на указанный месяц. "
                    "Используйте редактирование правила."
                ),
            }

        rule_id = await db.fetchval(
            """
            INSERT INTO user_cashback_rules(
                user_id, user_card_id, cashback_category_id, year, month, percent, created_at, updated_at
            )
            VALUES($1, $2, $3, $4, $5, $6, NOW(), NOW())
            RETURNING id
            """,
            str(user_id),
            user_card_id,
            cashback_category_id,
            year,
            month,
            float(percent),
        )
        log_event(
            logger,
            "cashback_rule_created",
            user_id=user_id,
            rule_id=rule_id,
            year=year,
            month=month,
        )
        return {"success": True, "rule_id": rule_id}
    except Exception as e:
        log_error(
            logger,
            e,
            "create_user_cashback_rule_error",
            user_id=user_id,
            year=year,
            month=month,
        )
        return {"success": False, "message": "Не удалось создать правило кэшбэка."}


async def edit_user_cashback_rule(user_id: int, rule_id: int, percent: float) -> Dict:
    if percent < 0 or percent > 100:
        return {"success": False, "message": "Процент должен быть в диапазоне от 0 до 100."}

    try:
        row = await db.fetchrow(
            """
            UPDATE user_cashback_rules
            SET percent = $1, updated_at = NOW()
            WHERE id = $2 AND user_id = $3
            RETURNING id
            """,
            float(percent),
            rule_id,
            str(user_id),
        )
        if not row:
            return {"success": False, "message": "Правило не найдено."}
        log_event(logger, "cashback_rule_updated", user_id=user_id, rule_id=rule_id)
        return {"success": True, "rule_id": row["id"]}
    except Exception as e:
        log_error(logger, e, "edit_user_cashback_rule_error", user_id=user_id, rule_id=rule_id)
        return {"success": False, "message": "Не удалось обновить правило."}


async def remove_user_cashback_rule(user_id: int, rule_id: int) -> Dict:
    try:
        row = await db.fetchrow(
            """
            DELETE FROM user_cashback_rules
            WHERE id = $1 AND user_id = $2
            RETURNING id
            """,
            rule_id,
            str(user_id),
        )
        if not row:
            return {"success": False, "message": "Правило не найдено."}
        log_event(logger, "cashback_rule_removed", user_id=user_id, rule_id=rule_id)
        return {"success": True, "rule_id": row["id"]}
    except Exception as e:
        log_error(logger, e, "remove_user_cashback_rule_error", user_id=user_id, rule_id=rule_id)
        return {"success": False, "message": "Не удалось удалить правило."}


async def _get_effective_rule_map(
    user_id: int,
    year: int,
    month: int,
    user_card_id: Optional[int] = None,
) -> Dict[str, Dict]:
    """
    Возвращает карту правил по нормализованному названию категории.

    Если user_card_id не указан, выбирается максимальный процент среди активных карт.
    """
    if user_card_id is not None:
        rows = await db.fetch(
            """
            SELECT
                LOWER(REGEXP_REPLACE(BTRIM(cc.name), '\\s+', ' ', 'g')) AS normalized_category_name,
                cc.name AS cashback_category_name,
                r.percent AS percent,
                uc.card_name AS card_name
            FROM user_cashback_rules r
            JOIN cashback_categories cc ON cc.id = r.cashback_category_id
            JOIN user_cards uc ON uc.id = r.user_card_id
            WHERE r.user_id = $1
              AND r.year = $2
              AND r.month = $3
              AND r.user_card_id = $4
              AND uc.is_active = TRUE
            """,
            str(user_id),
            year,
            month,
            user_card_id,
        )
    else:
        rows = await db.fetch(
            """
            WITH ranked_rules AS (
                SELECT
                    LOWER(REGEXP_REPLACE(BTRIM(cc.name), '\\s+', ' ', 'g')) AS normalized_category_name,
                    cc.name AS cashback_category_name,
                    uc.card_name AS card_name,
                    r.percent AS percent,
                    ROW_NUMBER() OVER (
                        PARTITION BY LOWER(REGEXP_REPLACE(BTRIM(cc.name), '\\s+', ' ', 'g'))
                        ORDER BY r.percent DESC, r.updated_at DESC, r.id DESC
                    ) AS rn
                FROM user_cashback_rules r
                JOIN cashback_categories cc ON cc.id = r.cashback_category_id
                JOIN user_cards uc ON uc.id = r.user_card_id
                WHERE r.user_id = $1
                  AND r.year = $2
                  AND r.month = $3
                  AND uc.is_active = TRUE
            )
            SELECT normalized_category_name, cashback_category_name, card_name, percent
            FROM ranked_rules
            WHERE rn = 1
            """,
            str(user_id),
            year,
            month,
        )

    rule_map: Dict[str, Dict] = {}
    for r in rows:
        key = r["normalized_category_name"]
        rule_map[key] = {
            "cashback_category_name": r["cashback_category_name"],
            "card_name": r["card_name"],
            "percent": float(r["percent"]),
        }
    return rule_map


async def calculate_potential_cashback_for_period(
    user_id: int,
    year: int,
    month: int,
    project_id: Optional[int] = None,
    user_card_id: Optional[int] = None,
) -> Dict:
    """
    Расчёт теоретического кэшбэка за указанный месяц.

    Важно: это приближённый расчёт по совпадению категорий.
    """
    try:
        if project_id is not None:
            from utils.permissions import Permission, has_permission

            if not await has_permission(user_id, project_id, Permission.VIEW_STATS):
                return {
                    "success": False,
                    "message": "Недостаточно прав для расчета кэшбэка по проекту.",
                }

        rule_map = await _get_effective_rule_map(user_id, year, month, user_card_id=user_card_id)

        if project_id is not None:
            expenses_rows = await db.fetch(
                """
                SELECT e.amount, c.name AS expense_category_name
                FROM expenses e
                JOIN categories c ON c.category_id = e.category_id
                WHERE e.project_id = $1
                  AND e.month = $2
                  AND EXTRACT(YEAR FROM e.date) = $3
                """,
                project_id,
                month,
                year,
            )
        else:
            expenses_rows = await db.fetch(
                """
                SELECT e.amount, c.name AS expense_category_name
                FROM expenses e
                JOIN categories c ON c.category_id = e.category_id
                WHERE e.user_id = $1
                  AND e.project_id IS NULL
                  AND e.month = $2
                  AND EXTRACT(YEAR FROM e.date) = $3
                """,
                str(user_id),
                month,
                year,
            )

        total_spent = 0.0
        total_potential_cashback = 0.0
        by_category: Dict[str, float] = {}
        matched_categories_count = 0

        for row in expenses_rows:
            amount = float(row["amount"] or 0)
            expense_category_name = row["expense_category_name"] or ""
            normalized_expense_category = _normalize_name(expense_category_name)

            total_spent += amount

            rule = rule_map.get(normalized_expense_category)
            if not rule:
                continue

            potential_cashback = amount * float(rule["percent"]) / 100.0
            total_potential_cashback += potential_cashback
            matched_categories_count += 1
            by_category[expense_category_name] = by_category.get(expense_category_name, 0.0) + potential_cashback

        effective_spent = total_spent - total_potential_cashback
        sorted_by_category = sorted(by_category.items(), key=lambda x: x[1], reverse=True)

        return {
            "success": True,
            "year": year,
            "month": month,
            "project_id": project_id,
            "total_spent": total_spent,
            "potential_cashback": total_potential_cashback,
            "effective_spent": effective_spent,
            "by_category": [
                {"category_name": category_name, "potential_cashback": value}
                for category_name, value in sorted_by_category
            ],
            "rules_applied_count": len(rule_map),
            "matched_expenses_count": matched_categories_count,
            "disclaimer": POTENTIAL_CASHBACK_DISCLAIMER,
        }
    except Exception as e:
        log_error(
            logger,
            e,
            "calculate_potential_cashback_for_period_error",
            user_id=user_id,
            year=year,
            month=month,
            project_id=project_id,
            user_card_id=user_card_id,
        )
        return {"success": False, "message": "Не удалось рассчитать теоретический кэшбэк."}


async def calculate_potential_cashback_for_last_12_months(
    user_id: int,
    project_id: Optional[int] = None,
    user_card_id: Optional[int] = None,
    reference_date: Optional[datetime.date] = None,
) -> Dict:
    """
    Агрегирует теоретический кэшбэк за скользящие 12 месяцев.
    """
    try:
        ref = reference_date or datetime.date.today()
        month_pairs: List[Tuple[int, int]] = []
        for offset in range(11, -1, -1):
            m = ref.month - offset
            y = ref.year
            while m <= 0:
                m += 12
                y -= 1
            month_pairs.append((y, m))

        totals = {
            "total_spent": 0.0,
            "potential_cashback": 0.0,
            "effective_spent": 0.0,
        }
        by_category: Dict[str, float] = {}

        for year, month in month_pairs:
            period = await calculate_potential_cashback_for_period(
                user_id=user_id,
                year=year,
                month=month,
                project_id=project_id,
                user_card_id=user_card_id,
            )
            if not period.get("success"):
                continue
            totals["total_spent"] += float(period["total_spent"])
            totals["potential_cashback"] += float(period["potential_cashback"])
            totals["effective_spent"] += float(period["effective_spent"])
            for item in period["by_category"]:
                category_name = item["category_name"]
                value = float(item["potential_cashback"])
                by_category[category_name] = by_category.get(category_name, 0.0) + value

        sorted_by_category = sorted(by_category.items(), key=lambda x: x[1], reverse=True)
        return {
            "success": True,
            "period_label": "Скользящие 12 месяцев",
            "total_spent": totals["total_spent"],
            "potential_cashback": totals["potential_cashback"],
            "effective_spent": totals["effective_spent"],
            "by_category": [
                {"category_name": category_name, "potential_cashback": value}
                for category_name, value in sorted_by_category
            ],
            "disclaimer": POTENTIAL_CASHBACK_DISCLAIMER,
        }
    except Exception as e:
        log_error(
            logger,
            e,
            "calculate_potential_cashback_for_last_12_months_error",
            user_id=user_id,
            project_id=project_id,
            user_card_id=user_card_id,
        )
        return {"success": False, "message": "Не удалось рассчитать кэшбэк за 12 месяцев."}


def format_cashback_summary(
    summary: Dict,
    title: Optional[str] = None,
    include_effective_spent: bool = True,
) -> str:
    """
    Форматирует расчёт теоретического кэшбэка в user-friendly текст.
    """
    if not summary or not summary.get("success"):
        return (
            "ℹ️ Нет данных для расчёта теоретического кэшбэка.\n\n"
            + POTENTIAL_CASHBACK_DISCLAIMER
        )

    header = title or "💳 Теоретический кэшбэк"
    lines = [
        header,
        f"💰 Потрачено всего: {_fmt_amount(float(summary.get('total_spent', 0.0)))}",
        f"💳 Теоретический кэшбэк: {_fmt_amount(float(summary.get('potential_cashback', 0.0)))}",
    ]
    if include_effective_spent:
        lines.append(
            f"📉 Эффективные траты: {_fmt_amount(float(summary.get('effective_spent', 0.0)))}"
        )

    by_category = summary.get("by_category") or []
    if by_category:
        lines.append("")
        lines.append("📊 Теоретический кэшбэк по категориям:")
        for item in by_category:
            lines.append(
                f"- {item['category_name']}: {_fmt_amount(float(item['potential_cashback']))}"
            )

    lines.append("")
    lines.append(POTENTIAL_CASHBACK_DISCLAIMER)
    return "\n".join(lines)
