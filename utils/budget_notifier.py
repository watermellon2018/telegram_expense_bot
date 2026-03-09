"""
Планировщик уведомлений о бюджете.
Запускается каждые 4 часа через APScheduler.

Логика уведомлений:
- Порог: spending >= notify_threshold → один раз, затем раз в 2 дня если траты изменились.
- Перерасход: spending > amount → один раз, затем раз в 2 дня если траты изменились.
- Если трат нет и не было → не беспокоить.
- Для проектов: уведомить ВСЕХ участников.
"""

import datetime
from utils.logger import get_logger, log_event, log_error
from utils import budgets as budgets_utils, excel
from utils.projects import get_project_members

logger = get_logger("utils.budget_notifier")

RESEND_INTERVAL_DAYS = 2  # Повторное уведомление не чаще чем раз в N дней


def _fmt_threshold_message(budget_amount: float, spending: float, threshold: float,
                            month_name: str, year: int) -> str:
    remaining = budget_amount - spending
    pct = spending / budget_amount * 100 if budget_amount > 0 else 0
    return (
        f"⚠️ Приближение к лимиту бюджета\n\n"
        f"📅 {month_name} {year}\n"
        f"💰 Бюджет: {budget_amount:,.0f}\u00a0руб.\n"
        f"💸 Потрачено: {spending:,.0f}\u00a0руб. ({pct:.0f}%)\n"
        f"🔻 Остаток: {remaining:,.0f}\u00a0руб.\n"
        f"📌 Порог уведомления: {threshold:,.0f}\u00a0руб."
    )


def _fmt_overspent_message(budget_amount: float, spending: float,
                           month_name: str, year: int) -> str:
    overspent = spending - budget_amount
    pct = spending / budget_amount * 100 if budget_amount > 0 else 0
    return (
        f"🚨 Бюджет превышен!\n\n"
        f"📅 {month_name} {year}\n"
        f"💰 Бюджет: {budget_amount:,.0f}\u00a0руб.\n"
        f"💸 Потрачено: {spending:,.0f}\u00a0руб. ({pct:.0f}%)\n"
        f"📈 Перерасход: {overspent:,.0f}\u00a0руб."
    )


def _should_send(notified_at, last_notified_spending, current_spending: float) -> bool:
    """
    Определяет, нужно ли отправлять уведомление.
    Условия:
    - Ещё не отправляли (notified_at IS NULL), ИЛИ
    - Прошло >= RESEND_INTERVAL_DAYS дней И траты изменились с момента последнего уведомления.
    """
    if notified_at is None:
        return True
    now = datetime.datetime.now(datetime.timezone.utc)
    # asyncpg возвращает timestamptz как aware datetime; приводим к единому типу
    if notified_at.tzinfo is None:
        notified_at = notified_at.replace(tzinfo=datetime.timezone.utc)
    days_passed = (now - notified_at).total_seconds() / 86400
    spending_changed = (last_notified_spending is None or
                        abs(current_spending - last_notified_spending) > 0.01)
    return days_passed >= RESEND_INTERVAL_DAYS and spending_changed


def _get_month_name(month: int) -> str:
    months = [
        "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
        "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"
    ]
    return months[month - 1]


async def _send_to_users(bot, user_ids: list[str], text: str) -> None:
    """Отправить сообщение списку пользователей."""
    for uid in user_ids:
        try:
            await bot.send_message(chat_id=int(uid), text=text)
        except Exception as e:
            log_error(logger, e, "budget_notification_send_error", user_id=uid)


async def check_budget_notifications(bot) -> None:
    """
    Основная функция планировщика.
    Проверяет все активные бюджеты и отправляет уведомления при необходимости.
    """
    now = datetime.datetime.now(datetime.timezone.utc)
    month = now.month
    year = now.year

    log_event(logger, "budget_check_start", month=month, year=year)

    active_budgets = await budgets_utils.get_all_active_budgets_with_notifications(month, year)
    log_event(logger, "budget_check_count", count=len(active_budgets))

    for budget in active_budgets:
        try:
            await _process_budget(bot, budget, month, year, now)
        except Exception as e:
            log_error(logger, e, "budget_check_error", budget_id=budget['id'])

    log_event(logger, "budget_check_done", month=month, year=year)


async def _process_budget(bot, budget: dict, month: int, year: int,
                          now: datetime.datetime) -> None:
    """Проверить один бюджет и отправить уведомления при необходимости."""
    user_id = budget['user_id']
    project_id = budget.get('project_id')
    budget_amount = budget['amount']
    threshold = budget.get('notify_threshold')

    # Получаем текущие траты за месяц
    expenses = await excel.get_month_expenses(int(user_id), month, year, project_id)
    current_spending = float(expenses.get('total', 0)) if expenses else 0.0

    # Нет трат — не беспокоим
    if current_spending == 0:
        return

    month_name = _get_month_name(month)
    last_spending = budget.get('last_notified_spending')

    # Собираем список получателей
    if project_id is not None:
        members = await get_project_members(project_id)
        recipient_ids = [m['user_id'] for m in members]
    else:
        recipient_ids = [str(user_id)]

    threshold_sent = False
    overspent_sent = False

    # --- Уведомление «порог достигнут» ---
    if threshold is not None and current_spending >= threshold:
        if _should_send(budget.get('threshold_notified_at'), last_spending, current_spending):
            msg = _fmt_threshold_message(budget_amount, current_spending, threshold, month_name, year)
            await _send_to_users(bot, recipient_ids, msg)
            threshold_sent = True
            log_event(logger, "threshold_notification_sent",
                      budget_id=budget['id'], user_id=user_id, project_id=project_id,
                      spending=current_spending, threshold=threshold)

    # --- Уведомление «бюджет превышен» ---
    if current_spending > budget_amount:
        if _should_send(budget.get('overspent_notified_at'), last_spending, current_spending):
            msg = _fmt_overspent_message(budget_amount, current_spending, month_name, year)
            await _send_to_users(bot, recipient_ids, msg)
            overspent_sent = True
            log_event(logger, "overspent_notification_sent",
                      budget_id=budget['id'], user_id=user_id, project_id=project_id,
                      spending=current_spending, budget=budget_amount)

    # Обновляем состояние уведомлений в БД
    if threshold_sent or overspent_sent:
        await budgets_utils.update_notification_state(
            budget_id=budget['id'],
            threshold_notified_at=now if threshold_sent else None,
            overspent_notified_at=now if overspent_sent else None,
            last_notified_spending=current_spending,
        )


async def check_user_budget_now(bot, user_id: int, project_id=None) -> None:
    """
    Немедленная проверка бюджета конкретного пользователя.
    Вызывается после изменения порога или суммы бюджета,
    чтобы не ждать следующего запуска планировщика (каждые 4 ч).
    """
    now = datetime.datetime.now(datetime.timezone.utc)
    month, year = now.month, now.year

    budget = await budgets_utils.get_budget(user_id, month, year, project_id)
    if not budget:
        return
    if not budget.get('notify_enabled') or not budget.get('notify_threshold'):
        return

    try:
        await _process_budget(bot, budget, month, year, now)
        log_event(logger, "check_user_budget_now_done",
                  user_id=user_id, project_id=project_id)
    except Exception as e:
        log_error(logger, e, "check_user_budget_now_error",
                  user_id=user_id, project_id=project_id)
