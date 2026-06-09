"""
Service слой: уведомление участников совместного проекта о новом расходе и об
отметке расхода как возможного дубликата (feature_110).

Правила уведомления о новом расходе — уведомляем только:
  - активных участников проекта (есть строка в project_members);
  - участников с правом просмотра расходов (VIEW_HISTORY);
  - тех, кто не отключил уведомления (режим != disabled);
  - для режима large_only — только если сумма >= индивидуального порога;
  - НЕ автора расхода.

Ошибка отправки одному получателю:
  - не откатывает создание расхода (расход уже закоммичен до вызова);
  - не мешает отправке остальным;
  - не выбрасывает необработанное исключение наружу;
  - логируется структурированно (project_id, expense_id, recipient_user_id,
    telegram_user_id, error_type, error_message).

Если Telegram сообщает, что пользователь заблокировал бота (Forbidden), это
логируется отдельным событием — в проекте нет отдельной системы дерегистрации
заблокировавших пользователей, поэтому участник из проекта НЕ удаляется.
"""

from decimal import Decimal
from typing import Optional

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

import config
import metrics
from utils import db, excel, expense_formatter, project_notifications, projects
from utils.logger import get_logger, log_error, log_event
from utils.permissions import Permission, has_permission

logger = get_logger("utils.project_notifier")

try:
    from telegram.error import Forbidden, TelegramError
except Exception:  # pragma: no cover
    Forbidden = Exception  # type: ignore[assignment,misc]
    TelegramError = Exception  # type: ignore[assignment,misc]


def _error_type(exc: Exception) -> str:
    """Короткое имя типа ошибки для структурированного лога (без высокой кардинальности)."""
    if isinstance(exc, Forbidden):
        return "forbidden"
    if isinstance(exc, TelegramError):
        return exc.__class__.__name__
    return exc.__class__.__name__


def _should_notify(settings: dict, amount: Decimal) -> bool:
    """Решает, нужно ли уведомлять участника с учётом его режима и порога."""
    mode = settings.get("expense_notify_mode", config.ExpenseNotifyMode.DEFAULT)

    if mode == config.ExpenseNotifyMode.DISABLED:
        return False

    if mode == config.ExpenseNotifyMode.LARGE_ONLY:
        threshold = settings.get("large_expense_threshold")
        if threshold is None:
            # Порог не задан — уведомляем (безопасный дефолт)
            return True
        return Decimal(str(amount)) >= Decimal(str(threshold))

    # ALL и любой неизвестный режим → уведомляем
    return True


def _notification_keyboard(expense_id: int) -> InlineKeyboardMarkup:
    """Inline-кнопки под уведомлением о новом расходе."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("👁 Посмотреть", callback_data=f"expnotif_view_{expense_id}"),
            InlineKeyboardButton("⚠️ Это дубликат", callback_data=f"expreport_{expense_id}"),
        ],
        [
            InlineKeyboardButton("🔕 Настройки уведомлений", callback_data="expnotif_settings"),
        ],
    ])


async def notify_expense_created(
    bot,
    *,
    expense_id: int,
    author_id: int,
) -> dict:
    """
    Уведомляет подходящих участников проекта о новом расходе.

    Вызывать ТОЛЬКО после успешного коммита транзакции создания расхода.

    Returns:
        {'sent': int, 'failed': int, 'skipped': int}
    """
    stats = {"sent": 0, "failed": 0, "skipped": 0}

    expense = await excel.get_expense_by_id(expense_id)
    if not expense:
        log_event(logger, "project_expense_notification_skip_no_expense",
                  expense_id=expense_id)
        return stats

    project_id = expense.get("project_id")
    if project_id is None:
        # Личный расход — никого не уведомляем
        return stats

    project = await projects.get_project_by_id(int(author_id), project_id)
    project_name = project["project_name"] if project else f"#{project_id}"

    author_name = await _resolve_user_name(bot, expense.get("user_id"))
    text = expense_formatter.format_expense_notification(project_name, expense, author_name)
    keyboard = _notification_keyboard(expense_id)

    amount = Decimal(str(expense["amount"]))

    try:
        members = await projects.get_project_members(project_id)
    except Exception as e:
        log_error(logger, e, "project_expense_notification_members_error",
                  project_id=project_id, expense_id=expense_id)
        return stats

    for member in members:
        recipient_user_id = member["user_id"]

        # Автору не отправляем
        if str(recipient_user_id) == str(author_id):
            continue

        # Право просмотра расходов
        if not await has_permission(int(recipient_user_id), project_id, Permission.VIEW_HISTORY):
            stats["skipped"] += 1
            continue

        # Индивидуальные настройки уведомлений
        settings = await project_notifications.get_member_settings(project_id, int(recipient_user_id))
        if not _should_notify(settings, amount):
            stats["skipped"] += 1
            continue

        # Отправка с изоляцией ошибок
        try:
            await bot.send_message(
                chat_id=int(recipient_user_id),
                text=text,
                reply_markup=keyboard,
            )
            stats["sent"] += 1
            log_event(logger, "project_expense_notification_sent",
                      project_id=project_id, expense_id=expense_id,
                      recipient_user_id=recipient_user_id)
        except Exception as exc:
            stats["failed"] += 1
            err_type = _error_type(exc)
            log_error(
                logger, exc, "project_expense_notification_failed",
                project_id=project_id,
                expense_id=expense_id,
                recipient_user_id=recipient_user_id,
                telegram_user_id=recipient_user_id,
                error_type=err_type,
                error_message=str(exc),
            )

    metrics.track_project_notification_sent(stats["sent"])
    metrics.track_project_notification_failed(stats["failed"])

    log_event(logger, "project_expense_notification_done",
              project_id=project_id, expense_id=expense_id,
              sent=stats["sent"], failed=stats["failed"], skipped=stats["skipped"])
    return stats


def _author_report_keyboard(expense_id: int, report_id: int) -> InlineKeyboardMarkup:
    """Кнопки для автора/владельца при уведомлении об отметке дубликата."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👁 Посмотреть", callback_data=f"expnotif_view_{expense_id}")],
        [
            InlineKeyboardButton("🗑 Удалить расход", callback_data=f"repdel_{report_id}_{expense_id}"),
            InlineKeyboardButton("✅ Оставить расход", callback_data=f"repkeep_{report_id}_{expense_id}"),
        ],
    ])


async def notify_duplicate_reported(
    bot,
    *,
    expense_id: int,
    report_id: int,
    reporter_id: int,
) -> dict:
    """
    Уведомляет автора расхода и владельца проекта об отметке возможного дубликата.

    Returns:
        {'sent': int, 'failed': int}
    """
    stats = {"sent": 0, "failed": 0}

    expense = await excel.get_expense_by_id(expense_id, include_deleted=True)
    if not expense:
        log_event(logger, "duplicate_report_notify_skip_no_expense", expense_id=expense_id)
        return stats

    project_id = expense.get("project_id")
    author_id = expense.get("user_id")

    project_name = f"#{project_id}"
    owner_id = None
    if project_id is not None:
        # Имя проекта и владелец — читаем напрямую (без проверки доступа конкретного юзера)
        row = await db.fetchrow(
            "SELECT project_name, user_id AS owner_id FROM projects WHERE project_id = $1",
            project_id,
        )
        if row:
            project_name = row["project_name"]
            owner_id = row["owner_id"]

    reporter_name = await _resolve_user_name(bot, str(reporter_id))
    text = expense_formatter.format_duplicate_report_to_author(project_name, expense, reporter_name)
    keyboard = _author_report_keyboard(expense_id, report_id)

    # Получатели: автор расхода + владелец проекта (без дублей, без самого reporter)
    recipients: list = []
    for uid in (author_id, owner_id):
        if uid is None:
            continue
        if str(uid) == str(reporter_id):
            continue
        if str(uid) not in [str(x) for x in recipients]:
            recipients.append(uid)

    for recipient_user_id in recipients:
        try:
            await bot.send_message(
                chat_id=int(recipient_user_id),
                text=text,
                reply_markup=keyboard,
            )
            stats["sent"] += 1
            log_event(logger, "duplicate_report_notification_sent",
                      project_id=project_id, expense_id=expense_id,
                      report_id=report_id, recipient_user_id=recipient_user_id)
        except Exception as exc:
            stats["failed"] += 1
            log_error(
                logger, exc, "duplicate_report_notification_failed",
                project_id=project_id,
                expense_id=expense_id,
                report_id=report_id,
                recipient_user_id=recipient_user_id,
                telegram_user_id=recipient_user_id,
                error_type=_error_type(exc),
                error_message=str(exc),
            )

    return stats


async def _resolve_user_name(bot, user_id) -> Optional[str]:
    """
    Пытается получить отображаемое имя пользователя через Telegram (get_chat).
    При ошибке возвращает None — форматтер сам подставит fallback на ID.
    """
    if user_id is None:
        return None
    try:
        chat = await bot.get_chat(int(user_id))
        # Предпочитаем имя, затем username
        name = getattr(chat, "first_name", None) or getattr(chat, "full_name", None)
        if not name:
            name = getattr(chat, "username", None)
        return name
    except Exception:
        return None
