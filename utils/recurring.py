"""
Утилиты для работы с постоянными расходами (recurring expenses).

Содержит:
- CRUD-операции над таблицей recurring_rules
- Вычисление следующей даты срабатывания (calculate_next_run)
- Планировщик автогенерации расходов (process_recurring_expenses)
- Вспомогательные функции форматирования
"""

import calendar
import datetime
from typing import Optional

from utils import db
from utils.logger import get_logger, log_event, log_error

logger = get_logger("utils.recurring")


# ---------------------------------------------------------------------------
# Вспомогательные функции
# ---------------------------------------------------------------------------

def format_frequency(rule: dict) -> str:
    """
    Возвращает человекочитаемое описание периодичности правила.

    Примеры:
      daily          → "каждый день"
      every_n_days   → "каждые 3 дня"
      weekly         → "каждую неделю"
      every_n_weeks  → "каждые 2 недели"
      monthly        → "каждый месяц"
      every_n_months → "каждые 3 месяца"
    """
    freq = rule['frequency_type']
    n = rule.get('interval_value')

    if freq == 'daily':
        return "каждый день"

    if freq == 'every_n_days':
        return f"каждые {n} {_days_word(n)}"

    if freq == 'weekly':
        return "каждую неделю"

    if freq == 'every_n_weeks':
        return f"каждые {n} {_weeks_word(n)}"

    if freq == 'monthly':
        dom = rule.get('day_of_month')
        if rule.get('is_last_day_of_month'):
            return "каждый месяц (последний день)"
        if dom:
            return f"каждый месяц {dom}-го числа"
        return "каждый месяц"

    if freq == 'every_n_months':
        return f"каждые {n} {_months_word(n)}"

    return freq  # fallback


def _days_word(n: int) -> str:
    """Склонение слова 'день' для числа n."""
    if 11 <= n % 100 <= 14:
        return "дней"
    r = n % 10
    if r == 1:
        return "день"
    if 2 <= r <= 4:
        return "дня"
    return "дней"


def _weeks_word(n: int) -> str:
    """Склонение слова 'неделя' для числа n."""
    if 11 <= n % 100 <= 14:
        return "недель"
    r = n % 10
    if r == 1:
        return "неделю"
    if 2 <= r <= 4:
        return "недели"
    return "недель"


def _months_word(n: int) -> str:
    """Склонение слова 'месяц' для числа n."""
    if 11 <= n % 100 <= 14:
        return "месяцев"
    r = n % 10
    if r == 1:
        return "месяц"
    if 2 <= r <= 4:
        return "месяца"
    return "месяцев"


# ---------------------------------------------------------------------------
# Вычисление следующей даты
# ---------------------------------------------------------------------------

def calculate_next_run(rule: dict, from_datetime: datetime.datetime) -> datetime.datetime:
    """
    Вычисляет следующее время срабатывания правила.

    Детерминированная функция без side-effects — только считает дату.
    Возвращает naive datetime (наивный UTC), как принято в проекте.

    Аргументы:
        rule:          словарь с полями из recurring_rules
        from_datetime: точка отсчёта (обычно текущий момент UTC)

    Алгоритм для каждого типа:
        daily           → +1 день от from_datetime
        every_n_days    → +interval_value дней
        weekly          → следующий целевой weekday (1-7 ISO)
                          если сегодня тот же weekday → +7 дней
        every_n_weeks   → +interval_value недель
        monthly         → тот же day_of_month следующего месяца
                          is_last_day_of_month → последний день месяца
                          clamp через calendar.monthrange (напр. 31 → 28 в феврале)
        every_n_months  → +interval_value месяцев; clamp day_of_month

    Edge cases:
        - Если вычисленная дата совпадает с from_datetime.date() — прибавляем ещё период
        - Февраль и короткие месяцы: day=min(target_day, last_day_of_month)
        - every_n_months через год: декабрь + 3 → март следующего года
    """
    base = from_datetime.date()
    freq = rule['frequency_type']

    if freq == 'daily':
        next_date = base + datetime.timedelta(days=1)

    elif freq == 'every_n_days':
        n = rule['interval_value']
        next_date = base + datetime.timedelta(days=n)

    elif freq == 'weekly':
        # weekday в правиле: 1=Пн, 7=Вс (ISO)
        # base.isoweekday(): 1=Пн, 7=Вс — совпадает
        target_wd = rule.get('weekday') or base.isoweekday()
        days_ahead = (target_wd - base.isoweekday()) % 7
        # Если сегодня тот же день недели — ждём следующей недели
        if days_ahead == 0:
            days_ahead = 7
        next_date = base + datetime.timedelta(days=days_ahead)

    elif freq == 'every_n_weeks':
        n = rule['interval_value']
        # Если задан конкретный weekday — идём к нему через N недель
        target_wd = rule.get('weekday') or base.isoweekday()
        days_ahead = (target_wd - base.isoweekday()) % 7
        if days_ahead == 0:
            days_ahead = 7 * n
        else:
            days_ahead += 7 * (n - 1)
        next_date = base + datetime.timedelta(days=days_ahead)

    elif freq == 'monthly':
        next_date = _next_monthly(base, rule, months_ahead=1)

    elif freq == 'every_n_months':
        n = rule['interval_value']
        next_date = _next_monthly(base, rule, months_ahead=n)

    else:
        # Неизвестный тип — fallback: +1 месяц
        next_date = _next_monthly(base, rule, months_ahead=1)

    # Дата не должна совпадать с сегодняшней (защита от зацикливания)
    if next_date <= base:
        next_date = base + datetime.timedelta(days=1)

    # Возвращаем naive UTC datetime (полночь следующей даты)
    return datetime.datetime.combine(next_date, datetime.time(0, 0, 0))


def _next_monthly(base: datetime.date, rule: dict, months_ahead: int) -> datetime.date:
    """
    Вычисляет дату через months_ahead месяцев от base.

    Учитывает:
        - is_last_day_of_month: берёт последний день нового месяца
        - day_of_month: пытается установить указанный день,
          clamp-ит до реального последнего дня (февраль, 30-дневные месяцы)
        - Если day_of_month не задан — сохраняет текущий день base
    """
    # Вычисляем целевой год и месяц
    total_months = (base.month - 1) + months_ahead
    target_year = base.year + total_months // 12
    target_month = total_months % 12 + 1

    last_day = calendar.monthrange(target_year, target_month)[1]

    if rule.get('is_last_day_of_month'):
        target_day = last_day
    else:
        target_day = rule.get('day_of_month') or base.day
        # Защита от 31 февраля и подобного
        target_day = min(target_day, last_day)

    return datetime.date(target_year, target_month, target_day)


# ---------------------------------------------------------------------------
# CRUD-операции
# ---------------------------------------------------------------------------

async def create_rule(
    user_id: str,
    amount: float,
    category_id: int,
    comment: str,
    project_id: Optional[int],
    frequency_type: str,
    interval_value: Optional[int],
    weekday: Optional[int],
    day_of_month: Optional[int],
    is_last_day_of_month: bool,
    start_date: datetime.date,
) -> Optional[int]:
    """
    Создаёт новое правило постоянного расхода.

    Если start_date <= сегодня, сразу создаёт первый расход за сегодня
    и планирует next_run_at на следующий период.
    Если start_date в будущем — первый расход будет создан воркером в start_date.

    Вычисляет начальный next_run_at детерминированно через calculate_next_run.
    Возвращает id созданной записи или None при ошибке.
    """
    # Формируем «пустой» объект правила для расчёта первой даты
    rule_proto = {
        'frequency_type': frequency_type,
        'interval_value': interval_value,
        'weekday': weekday,
        'day_of_month': day_of_month,
        'is_last_day_of_month': is_last_day_of_month,
    }
    now = datetime.datetime.utcnow()
    today = now.date()

    # Если правило запускается сегодня (или задним числом), сразу создаём первый расход
    # и двигаем next_run_at на следующий период.
    if start_date <= today:
        next_run_at = calculate_next_run(rule_proto, now)
    else:
        # Для будущей даты стартуем ровно в start_date (без немедленного расхода).
        next_run_at = datetime.datetime.combine(start_date, datetime.time(0, 0, 0))

    try:
        rule_id = await db.fetchval(
            """
            INSERT INTO recurring_rules
                (user_id, amount, category_id, comment, project_id,
                 frequency_type, interval_value, weekday, day_of_month,
                 is_last_day_of_month, start_date, next_run_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
            RETURNING id
            """,
            user_id, float(amount), int(category_id), comment or '',
            project_id, frequency_type, interval_value, weekday,
            day_of_month, is_last_day_of_month, start_date, next_run_at,
        )

        # Немедленно создаём первый расход за сегодня, если правило уже активно.
        # Это нужно, чтобы /day сразу показывал новую запись.
        if start_date <= today:
            await db.execute(
                """
                INSERT INTO expenses
                    (user_id, project_id, date, time, amount, category_id,
                     description, month, source_type, recurring_rule_id, created_by_system)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, 'recurring', $9, TRUE)
                """,
                user_id,
                project_id,
                today,
                now.time().replace(microsecond=0),
                float(amount),
                int(category_id),
                comment,
                today.month,
                rule_id,
            )

        log_event(logger, "recurring_rule_created",
                  user_id=user_id, rule_id=rule_id, frequency_type=frequency_type,
                  initial_expense_created=(start_date <= today), next_run_at=str(next_run_at))
        return rule_id
    except Exception as e:
        log_error(logger, e, "recurring_rule_create_error",
                  user_id=user_id, frequency_type=frequency_type)
        return None


async def get_rules_for_user(
    user_id: str,
    project_id: Optional[int] = None,
) -> list:
    """
    Возвращает все правила пользователя.

    Для project_id=None — только личные правила (project_id IS NULL).
    Для конкретного project_id — правила этого проекта.
    Сортировка: active первыми, затем по amount DESC.
    """
    try:
        if project_id is None:
            rows = await db.fetch(
                """
                SELECT rr.*, c.name AS category_name
                FROM recurring_rules rr
                JOIN categories c ON c.category_id = rr.category_id
                WHERE rr.user_id = $1 AND rr.project_id IS NULL
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
                FROM recurring_rules rr
                JOIN categories c ON c.category_id = rr.category_id
                WHERE rr.user_id = $1 AND rr.project_id = $2
                ORDER BY
                    CASE WHEN rr.status = 'active' THEN 0 ELSE 1 END,
                    rr.amount DESC
                """,
                user_id, project_id,
            )
        return [dict(r) for r in rows]
    except Exception as e:
        log_error(logger, e, "recurring_get_rules_error", user_id=user_id)
        return []


async def get_rule_by_id(rule_id: int, user_id: str) -> Optional[dict]:
    """
    Возвращает правило по id с проверкой принадлежности пользователю.
    Возвращает None если правило не найдено или не принадлежит user_id.
    """
    try:
        row = await db.fetchrow(
            """
            SELECT rr.*, c.name AS category_name
            FROM recurring_rules rr
            JOIN categories c ON c.category_id = rr.category_id
            WHERE rr.id = $1 AND rr.user_id = $2
            """,
            rule_id, user_id,
        )
        return dict(row) if row else None
    except Exception as e:
        log_error(logger, e, "recurring_get_rule_error", rule_id=rule_id, user_id=user_id)
        return None


async def delete_rule(rule_id: int, user_id: str) -> bool:
    """
    Удаляет правило пользователя.
    Связанные расходы сохраняются (recurring_rule_id → NULL через ON DELETE SET NULL).
    """
    try:
        result = await db.execute(
            "DELETE FROM recurring_rules WHERE id = $1 AND user_id = $2",
            rule_id, user_id,
        )
        deleted = result != "DELETE 0"
        if deleted:
            log_event(logger, "recurring_rule_deleted", rule_id=rule_id, user_id=user_id)
        return deleted
    except Exception as e:
        log_error(logger, e, "recurring_rule_delete_error", rule_id=rule_id, user_id=user_id)
        return False


async def pause_rule(rule_id: int, user_id: str) -> bool:
    """Приостанавливает правило (status = 'paused')."""
    try:
        result = await db.execute(
            """
            UPDATE recurring_rules
            SET status = 'paused', updated_at = now()
            WHERE id = $1 AND user_id = $2 AND status = 'active'
            """,
            rule_id, user_id,
        )
        updated = result != "UPDATE 0"
        if updated:
            log_event(logger, "recurring_rule_paused", rule_id=rule_id, user_id=user_id)
        return updated
    except Exception as e:
        log_error(logger, e, "recurring_rule_pause_error", rule_id=rule_id, user_id=user_id)
        return False


async def resume_rule(rule_id: int, user_id: str) -> bool:
    """
    Возобновляет правило (status = 'active').
    Пересчитывает next_run_at от текущего момента, чтобы не накапливались
    пропущенные срабатывания за период паузы.
    """
    try:
        row = await db.fetchrow(
            "SELECT * FROM recurring_rules WHERE id = $1 AND user_id = $2",
            rule_id, user_id,
        )
        if not row or row['status'] != 'paused':
            return False

        now = datetime.datetime.utcnow()
        next_run = calculate_next_run(dict(row), now)

        result = await db.execute(
            """
            UPDATE recurring_rules
            SET status = 'active', next_run_at = $1, updated_at = now()
            WHERE id = $2 AND user_id = $3
            """,
            next_run, rule_id, user_id,
        )
        updated = result != "UPDATE 0"
        if updated:
            log_event(logger, "recurring_rule_resumed",
                      rule_id=rule_id, user_id=user_id, next_run=str(next_run))
        return updated
    except Exception as e:
        log_error(logger, e, "recurring_rule_resume_error", rule_id=rule_id, user_id=user_id)
        return False


async def update_rule_schedule(
    rule_id: int,
    user_id: str,
    frequency_type: str,
    interval_value: Optional[int] = None,
    weekday: Optional[int] = None,
    day_of_month: Optional[int] = None,
    is_last_day_of_month: bool = False,
) -> Optional[datetime.datetime]:
    """
    Обновляет параметры периодичности правила и пересчитывает next_run_at.

    Важно:
    - Изменение применяется с текущего момента (UTC).
    - После редактирования следующее срабатывание всегда в будущем
      (calculate_next_run гарантирует это).

    Возвращает:
        next_run_at (datetime) при успешном обновлении,
        None если правило не найдено/не принадлежит пользователю или при ошибке.
    """
    now = datetime.datetime.utcnow()
    rule_for_calc = {
        'frequency_type': frequency_type,
        'interval_value': interval_value,
        'weekday': weekday,
        'day_of_month': day_of_month,
        'is_last_day_of_month': is_last_day_of_month,
    }
    next_run = calculate_next_run(rule_for_calc, now)

    try:
        result = await db.execute(
            """
            UPDATE recurring_rules
            SET frequency_type = $1,
                interval_value = $2,
                weekday = $3,
                day_of_month = $4,
                is_last_day_of_month = $5,
                next_run_at = $6,
                updated_at = now()
            WHERE id = $7 AND user_id = $8
            """,
            frequency_type,
            interval_value,
            weekday,
            day_of_month,
            is_last_day_of_month,
            next_run,
            rule_id,
            user_id,
        )
        if result == "UPDATE 0":
            return None

        log_event(
            logger,
            "recurring_rule_schedule_updated",
            user_id=user_id,
            rule_id=rule_id,
            frequency_type=frequency_type,
            next_run_at=str(next_run),
        )
        return next_run
    except Exception as e:
        log_error(logger, e, "recurring_rule_schedule_update_error", rule_id=rule_id, user_id=user_id)
        return None


# ---------------------------------------------------------------------------
# Планировщик: автогенерация расходов
# ---------------------------------------------------------------------------

async def process_recurring_expenses(bot) -> None:
    """
    Основная функция планировщика постоянных расходов.
    Запускается каждые 5 минут через APScheduler (настройка в main.py).

    Алгоритм:
    1. Выбрать все активные правила с next_run_at <= now (UTC)
    2. Для каждого правила:
       a. Проверить idempotency: нет ли уже расхода с этим rule_id за сегодня
       b. Создать расход напрямую через SQL (без excel.add_expense — у воркера
          системные права, permission check не нужен)
       c. Отправить уведомление пользователю
       d. Вычислить следующий next_run_at и обновить правило
    3. Логировать итоги

    Важно:
    - Если воркер не работал несколько дней, пропущенные периоды НЕ backfill-ятся —
      только один расход за текущий день, затем next_run_at обновляется вперёд
    - Все datetime — naive UTC (как в остальном проекте)
    """
    now = datetime.datetime.utcnow()
    today = now.date()
    current_time = now.time().replace(microsecond=0)

    try:
        # Выбираем только активные правила, чей срок пришёл
        rules = await db.fetch(
            """
            SELECT rr.*, c.name AS category_name
            FROM recurring_rules rr
            JOIN categories c ON c.category_id = rr.category_id
            WHERE rr.status = 'active' AND rr.next_run_at <= $1
            """,
            now,
        )
    except Exception as e:
        log_error(logger, e, "recurring_scheduler_fetch_error")
        return

    if not rules:
        return

    processed = 0
    skipped = 0
    errors = 0

    for row in rules:
        rule = dict(row)
        rule_id = rule['id']

        try:
            # --- Проверка идемпотентности ---
            # Не создаём дубль, если расход за сегодня уже есть
            already_created = await db.fetchval(
                """
                SELECT 1 FROM expenses
                WHERE recurring_rule_id = $1 AND date = $2
                LIMIT 1
                """,
                rule_id, today,
            )
            if already_created:
                skipped += 1
                continue

            # --- Создаём расход ---
            await db.execute(
                """
                INSERT INTO expenses
                    (user_id, project_id, date, time, amount, category_id,
                     description, month, source_type, recurring_rule_id, created_by_system)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, 'recurring', $9, TRUE)
                """,
                rule['user_id'],
                rule['project_id'],
                today,
                current_time,
                float(rule['amount']),
                rule['category_id'],
                rule['comment'] or None,
                today.month,
                rule_id,
            )

            # --- Уведомляем пользователя ---
            freq_text = format_frequency(rule)
            cat_name = rule.get('category_name', '')
            comment_text = rule['comment'] or cat_name
            try:
                await bot.send_message(
                    chat_id=rule['user_id'],
                    text=(
                        f"🔁 Добавлен постоянный расход:\n"
                        f"💰 {rule['amount']} — {comment_text}\n"
                        f"📅 {freq_text}"
                    ),
                )
            except Exception as notify_err:
                # Ошибка уведомления не должна отменять создание расхода
                log_error(logger, notify_err, "recurring_notify_error",
                          rule_id=rule_id, user_id=rule['user_id'])

            # --- Обновляем next_run_at ---
            next_run = calculate_next_run(rule, now)
            await db.execute(
                """
                UPDATE recurring_rules
                SET next_run_at = $1, updated_at = now()
                WHERE id = $2
                """,
                next_run, rule_id,
            )

            processed += 1
            log_event(logger, "recurring_expense_created",
                      rule_id=rule_id, user_id=rule['user_id'],
                      amount=rule['amount'], next_run=str(next_run))

        except Exception as e:
            errors += 1
            log_error(logger, e, "recurring_rule_process_error",
                      rule_id=rule_id, user_id=rule.get('user_id'))

    log_event(logger, "recurring_scheduler_done",
              processed=processed, skipped=skipped, errors=errors,
              total=len(rules))
