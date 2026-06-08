"""
Service слой: поиск потенциальных дубликатов расходов и идемпотентное создание
расхода в совместном проекте (feature_110).

Проверка полностью детерминированная (без ML/LLM/внешних API).

Расход считается потенциальным дубликатом, если в том же проекте:
  - расход добавлен ДРУГИМ участником;
  - совпадает дата расхода;
  - совпадает категория;
  - сумма совпадает точно либо в пределах DUPLICATE_EXPENSE_AMOUNT_TOLERANCE_PERCENT;
  - существующий расход создан недавно (в пределах DUPLICATE_EXPENSE_TIME_WINDOW_MINUTES);
  - расход не удалён (deleted_at IS NULL).

Комментарий используется только как дополнительный сигнал ранжирования —
отсутствие или различие комментариев не исключает дубликат.

При нескольких совпадениях выбирается самый похожий (по близости суммы), а при
равенстве — самый свежий.
"""

import datetime
from decimal import Decimal
from typing import Optional

import config
from utils import db, excel
from utils.logger import get_logger, log_event, log_error
from utils.permissions import Permission, has_permission

logger = get_logger("utils.duplicate_service")


def _normalize_comment(comment: Optional[str]) -> str:
    """Нормализует комментарий для сравнения (нижний регистр, без лишних пробелов)."""
    if not comment:
        return ""
    return " ".join(comment.lower().split())


def _amount_within_tolerance(a: Decimal, b: Decimal, tolerance_percent: float) -> bool:
    """
    True, если суммы совпадают точно или отличаются не более чем на tolerance_percent
    относительно большей из них.
    """
    a = Decimal(str(a))
    b = Decimal(str(b))
    if a == b:
        return True
    larger = max(abs(a), abs(b))
    if larger == 0:
        return True
    diff_percent = abs(a - b) / larger * Decimal(100)
    return diff_percent <= Decimal(str(tolerance_percent))


async def is_shared_project(project_id: Optional[int]) -> bool:
    """Проверяет, что проект существует и имеет больше одного участника."""
    if project_id is None:
        return False
    try:
        count = await db.fetchval(
            "SELECT COUNT(*) FROM project_members WHERE project_id = $1",
            project_id,
        )
        return (count or 0) > 1
    except Exception as e:
        log_error(logger, e, "is_shared_project_error", project_id=project_id)
        return False


async def find_possible_duplicate(
    *,
    project_id: int,
    author_id: int,
    amount,
    category_id: int,
    expense_date: datetime.date,
    created_at: Optional[datetime.datetime] = None,
    comment: Optional[str] = None,
    conn=None,
) -> Optional[dict]:
    """
    Ищет наиболее похожий потенциальный дубликат расхода в совместном проекте.

    Args:
        project_id:   проект, в который добавляется расход
        author_id:    автор нового расхода (его собственные расходы исключаются)
        amount:       сумма нового расхода
        category_id:  категория нового расхода
        expense_date: дата нового расхода
        created_at:   точка отсчёта временного окна (по умолчанию now())
        comment:      комментарий нового расхода (доп. сигнал ранжирования)
        conn:         опциональное соединение/транзакция для согласованного чтения

    Returns:
        dict с данными найденного расхода (включая category_name и author_id) или None.
    """
    if project_id is None:
        return None

    now = created_at or datetime.datetime.now()
    window = datetime.timedelta(minutes=config.DUPLICATE_EXPENSE_TIME_WINDOW_MINUTES)
    earliest = now - window
    tolerance = config.DUPLICATE_EXPENSE_AMOUNT_TOLERANCE_PERCENT

    sql = """
        SELECT e.id, e.user_id AS author_id, e.amount, e.category_id,
               e.date, e.time, e.description, e.created_at,
               c.name AS category_name
        FROM expenses e
        JOIN categories c ON e.category_id = c.category_id
        WHERE e.project_id = $1
          AND e.category_id = $2
          AND e.date = $3
          AND e.user_id <> $4
          AND e.deleted_at IS NULL
          AND e.created_at >= $5
        ORDER BY e.created_at DESC
    """
    params = (project_id, int(category_id), expense_date, str(author_id), earliest)

    try:
        if conn is not None:
            rows = await conn.fetch(sql, *params)
        else:
            rows = await db.fetch(sql, *params)
    except Exception as e:
        log_error(logger, e, "find_possible_duplicate_query_error",
                  project_id=project_id, author_id=author_id, category_id=category_id)
        return None

    if not rows:
        return None

    target_amount = Decimal(str(amount))
    target_comment = _normalize_comment(comment)

    # Отбираем кандидатов, у которых сумма в пределах допуска
    candidates = []
    for r in rows:
        cand_amount = Decimal(str(r["amount"]))
        if not _amount_within_tolerance(target_amount, cand_amount, tolerance):
            continue
        candidates.append(r)

    if not candidates:
        return None

    # Ранжирование: сначала наименьшая разница в сумме, затем совпадение комментария,
    # затем самый свежий (created_at). Комментарий — только доп. сигнал, поэтому
    # влияет лишь при равной близости суммы.
    def _rank_key(r):
        cand_amount = Decimal(str(r["amount"]))
        amount_diff = abs(target_amount - cand_amount)
        # Совпадение комментария даёт небольшой приоритет (0 лучше, чем 1)
        comment_match = 0
        if target_comment and _normalize_comment(r["description"]) == target_comment:
            comment_match = 0
        else:
            comment_match = 1
        created = r["created_at"] or datetime.datetime.min
        # сортируем по: amount_diff ASC, comment_match ASC, created DESC
        return (amount_diff, comment_match, -created.timestamp())

    best = min(candidates, key=_rank_key)
    result = dict(best)

    log_event(logger, "possible_expense_duplicate_found",
              project_id=project_id, author_id=author_id,
              category_id=category_id, expense_id=result["id"],
              candidates_count=len(candidates))
    return result


async def create_expense_idempotent(
    *,
    author_id: int,
    amount,
    category_id: int,
    description: str,
    project_id: Optional[int],
    idempotency_key: Optional[str] = None,
    bot_data: Optional[dict] = None,
) -> dict:
    """
    Идемпотентно создаёт расход.

    Защита от двойного создания строится на двух уровнях:
      1. idempotency_key (например, id черновика расхода): если для этого ключа
         расход уже создавался в этом процессе, повторное создание не происходит.
         Кэш ключей живёт в bot_data (как cooldown в recurring) — переживает
         переходы между апдейтами, но не рестарт процесса.
      2. PostgreSQL advisory lock по проекту в рамках транзакции — сериализует
         одновременные вставки в один проект (защита от race condition между
         процессами/воркерами).

    Возвращает dict:
        {'created': bool, 'expense_id': Optional[int], 'duplicate_of': Optional[int]}
    """
    result = {"created": False, "expense_id": None, "duplicate_of": None}

    # --- Уровень 1: idempotency key в bot_data ---
    cache = None
    if bot_data is not None and idempotency_key:
        cache = bot_data.setdefault("expense_idempotency", {})
        if idempotency_key in cache:
            existing_id = cache[idempotency_key]
            log_event(logger, "create_expense_idempotent_cache_hit",
                      idempotency_key=idempotency_key, expense_id=existing_id)
            result["expense_id"] = existing_id
            result["created"] = False
            return result

    project_id_norm = excel._normalize_project_id(project_id)

    try:
        # Для проектов берём транзакционный advisory lock, чтобы проверка дубля
        # и вставка были атомарны относительно других участников.
        async with db.transaction() as conn:
            async with conn.transaction():
                if project_id_norm is not None:
                    await excel.acquire_project_expense_lock(conn, project_id_norm)

                expense_id = await excel.create_expense(
                    author_id, amount, category_id, description,
                    project_id_norm, conn=conn,
                )

        if expense_id is None:
            log_error(logger, Exception("create_expense returned None"),
                      "create_expense_idempotent_failed",
                      author_id=author_id, project_id=project_id_norm)
            return result

        result["created"] = True
        result["expense_id"] = expense_id

        if cache is not None and idempotency_key:
            cache[idempotency_key] = expense_id

        log_event(logger, "create_expense_idempotent_success",
                  author_id=author_id, project_id=project_id_norm,
                  expense_id=expense_id, idempotency_key=idempotency_key)
        return result
    except Exception as e:
        log_error(logger, e, "create_expense_idempotent_error",
                  author_id=author_id, project_id=project_id_norm)
        return result


async def should_check_duplicates(user_id: int, project_id: Optional[int]) -> bool:
    """
    Проверка дубликатов нужна только если:
      - есть активный проект (project_id не None);
      - в проекте больше одного участника;
      - пользователь имеет право добавлять расходы.
    """
    if project_id is None:
        return False
    if not await has_permission(user_id, project_id, Permission.ADD_EXPENSE):
        return False
    return await is_shared_project(project_id)
