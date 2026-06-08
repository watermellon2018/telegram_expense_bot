"""
Оркестрация создания расхода с защитой от дубликатов (feature_110).

Единая точка, через которую и FSM-диалог, и callback-подтверждение создают
расход. Это гарантирует одинаковое поведение (идемпотентность + уведомления)
и отсутствие дублирования бизнес-логики в handlers.

Поток:
  1. process_new_expense(...) — вызывается из диалога/текстового хендлера.
     - Если проверка дубликатов не нужна (личный расход / один участник /
       нет прав) → сразу идемпотентно создаём расход и уведомляем.
     - Если найден потенциальный дубликат → НЕ создаём, сохраняем черновик в
       bot_data и возвращаем информацию для показа предупреждения.
     - Если дубликат не найден → создаём и уведомляем.
  2. confirm_pending_expense(...) — вызывается из callback «Всё равно добавить».
     - Создаёт расход по сохранённому черновику (идемпотентно) и уведомляет.
"""

import asyncio
import datetime
import secrets
from typing import Optional

import metrics
from utils import duplicate_service, project_notifier
from utils.logger import get_logger, log_event, log_error

logger = get_logger("utils.expense_creation")

# Ключ в bot_data, под которым хранятся черновики ожидающих подтверждения расходов
_PENDING_KEY = "pending_duplicate_expenses"


def _store_draft(bot_data: dict, owner_user_id: int, draft: dict) -> str:
    """Сохраняет черновик расхода в bot_data, возвращает draft_id (idempotency key)."""
    drafts = bot_data.setdefault(_PENDING_KEY, {})
    # Случайный, неугадываемый id — нельзя подделать в callback data
    draft_id = secrets.token_hex(8)
    draft["owner_user_id"] = str(owner_user_id)
    draft["created_ts"] = datetime.datetime.now().timestamp()
    drafts[draft_id] = draft
    return draft_id


def get_draft(bot_data: Optional[dict], draft_id: str) -> Optional[dict]:
    """Возвращает черновик по id (или None)."""
    if not bot_data:
        return None
    return bot_data.get(_PENDING_KEY, {}).get(draft_id)


def discard_draft(bot_data: Optional[dict], draft_id: str) -> None:
    """Удаляет черновик (после подтверждения/отмены)."""
    if not bot_data:
        return
    bot_data.get(_PENDING_KEY, {}).pop(draft_id, None)


async def _create_and_notify(
    bot,
    *,
    author_id: int,
    amount,
    category_id: int,
    description: str,
    project_id: Optional[int],
    idempotency_key: Optional[str],
    bot_data: Optional[dict],
) -> Optional[int]:
    """Идемпотентно создаёт расход и (для проектов) запускает уведомления."""
    result = await duplicate_service.create_expense_idempotent(
        author_id=author_id,
        amount=amount,
        category_id=category_id,
        description=description,
        project_id=project_id,
        idempotency_key=idempotency_key,
        bot_data=bot_data,
    )

    expense_id = result.get("expense_id")
    if expense_id is None:
        return None

    # Уведомляем участников только если расход реально создан сейчас (не повтор)
    # и это проектный расход.
    if result.get("created") and project_id is not None:
        # Неблокирующе: ошибка уведомления не должна влиять на ответ пользователю.
        asyncio.create_task(
            _safe_notify(bot, expense_id=expense_id, author_id=author_id)
        )

    return expense_id


async def _safe_notify(bot, *, expense_id: int, author_id: int) -> None:
    """Обёртка для фоновой задачи уведомления — глушит исключения с логом."""
    try:
        await project_notifier.notify_expense_created(
            bot, expense_id=expense_id, author_id=author_id
        )
    except Exception as e:
        log_error(logger, e, "notify_expense_created_task_error",
                  expense_id=expense_id, author_id=author_id)


async def process_new_expense(
    bot,
    *,
    author_id: int,
    amount,
    category_id: int,
    category_name: str,
    description: str,
    project_id: Optional[int],
    bot_data: Optional[dict],
) -> dict:
    """
    Главная точка обработки нового расхода с проверкой дубликата.

    Returns dict:
        {'status': 'created', 'expense_id': int}
            расход создан сразу (проверка не нужна или дубль не найден)
        {'status': 'duplicate', 'draft_id': str, 'existing': dict}
            найден потенциальный дубль, расход НЕ создан, нужно показать предупреждение
        {'status': 'error'}
            не удалось создать расход
    """
    # Нужна ли вообще проверка дубликатов?
    need_check = await duplicate_service.should_check_duplicates(author_id, project_id)

    if need_check:
        existing = await duplicate_service.find_possible_duplicate(
            project_id=project_id,
            author_id=author_id,
            amount=amount,
            category_id=category_id,
            expense_date=datetime.date.today(),
            created_at=datetime.datetime.now(),
            comment=description,
        )
        if existing is not None:
            metrics.track_duplicate_found()
            draft = {
                "author_id": str(author_id),
                "amount": float(amount),
                "category_id": int(category_id),
                "category_name": category_name,
                "description": description or "",
                "project_id": project_id,
            }
            draft_id = _store_draft(bot_data, author_id, draft)
            log_event(logger, "possible_expense_duplicate_prompt",
                      author_id=author_id, project_id=project_id,
                      existing_expense_id=existing["id"], draft_id=draft_id)
            return {"status": "duplicate", "draft_id": draft_id, "existing": existing}

    # Дубль не найден или проверка не нужна — создаём сразу
    expense_id = await _create_and_notify(
        bot,
        author_id=author_id,
        amount=amount,
        category_id=category_id,
        description=description,
        project_id=project_id,
        idempotency_key=None,
        bot_data=bot_data,
    )
    if expense_id is None:
        return {"status": "error"}
    return {"status": "created", "expense_id": expense_id}


async def confirm_pending_expense(
    bot,
    *,
    draft_id: str,
    bot_data: Optional[dict],
) -> dict:
    """
    Создаёт расход по сохранённому черновику (подтверждение «Всё равно добавить»).

    Идемпотентно: повторное подтверждение того же draft_id не создаст второй расход
    (idempotency_key = draft_id кэшируется в bot_data).

    Returns:
        {'status': 'created'|'already'|'expired'|'error', 'expense_id': Optional[int]}
    """
    draft = get_draft(bot_data, draft_id)
    if draft is None:
        return {"status": "expired", "expense_id": None}

    # Проверяем, не создавался ли уже расход по этому черновику
    cache = (bot_data or {}).get("expense_idempotency", {})
    already = draft_id in cache

    expense_id = await _create_and_notify(
        bot,
        author_id=int(draft["author_id"]),
        amount=draft["amount"],
        category_id=draft["category_id"],
        description=draft.get("description", ""),
        project_id=draft.get("project_id"),
        idempotency_key=draft_id,
        bot_data=bot_data,
    )

    if expense_id is None:
        return {"status": "error", "expense_id": None}

    if already:
        return {"status": "already", "expense_id": expense_id}

    metrics.track_duplicate_confirmed()
    log_event(logger, "possible_expense_duplicate_confirmed",
              draft_id=draft_id, expense_id=expense_id)
    return {"status": "created", "expense_id": expense_id}
