"""
Обработчики команд для управления бюджетом.

Меню бюджета (кнопка «💰 Бюджет» в главном меню):
  📊 Статус бюджета      — текущий бюджет vs. траты
  💰 Установить бюджет   — диалог: сумма → уведомления → порог
  🔔 Настроить уведомление — изменить порог или включить уведомления
  🔕 Отключить уведомления — выключить оповещения
  ⬅️ Главное меню
"""

import datetime
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    ContextTypes,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    filters,
)
from utils import excel
from utils import budgets as budgets_utils
from utils.permissions import Permission, has_permission
from utils.helpers import get_main_menu_keyboard, main_menu_button_regex
from utils.logger import get_logger, log_event, log_error
import config

logger = get_logger("handlers.budget")

# ---------------------------------------------------------------------------
# Состояния диалогов
# ---------------------------------------------------------------------------
(
    ENTERING_AMOUNT,
    ASKING_NOTIFY,
    ENTERING_THRESHOLD,
    EDITING_THRESHOLD,
) = range(4)


# ---------------------------------------------------------------------------
# Вспомогательные функции
# ---------------------------------------------------------------------------

def _budget_menu_keyboard() -> ReplyKeyboardMarkup:
    btn = config.BUDGET_MENU_BUTTONS
    keyboard = [
        [btn["status"],  btn["set"]],
        [btn["edit_notify"], btn["disable_notify"], btn["back"]],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def _budget_menu_button_regex(key: str) -> str:
    import re
    return "^" + re.escape(config.BUDGET_MENU_BUTTONS[key]) + "$"


def _fmt_amount(value: float) -> str:
    return f"{value:,.0f}".replace(",", "\u202f") + "\u00a0руб."


def _progress_bar(spent: float, budget: float, length: int = 10) -> str:
    """Текстовый прогресс-бар: ████░░░░░░ 65%"""
    if budget <= 0:
        return ""
    pct = min(spent / budget, 1.0)
    filled = round(pct * length)
    bar = "█" * filled + "░" * (length - filled)
    return f"[{bar}] {pct * 100:.0f}%"


def _format_budget_status_text(budget: dict, spending: float,
                                month: int, year: int) -> str:
    """Формирует текстовый статус бюджета."""
    from utils.helpers import get_month_name
    month_name = get_month_name(month)
    budget_amount = budget['amount']
    bar = _progress_bar(spending, budget_amount)

    if spending <= budget_amount:
        remaining = budget_amount - spending
        status_line = f"✅ Остаток: {_fmt_amount(remaining)}"
    else:
        overspent = spending - budget_amount
        status_line = f"❌ Перерасход: {_fmt_amount(overspent)}"

    lines = [
        f"📊 Бюджет на {month_name} {year}",
        "",
        f"💰 Установлен: {_fmt_amount(budget_amount)}",
        f"💸 Потрачено:  {_fmt_amount(spending)}",
        f"   {bar}",
        status_line,
    ]

    if budget.get('notify_enabled') and budget.get('notify_threshold'):
        lines.append(f"🔔 Порог уведомления: {_fmt_amount(budget['notify_threshold'])}")
    elif not budget.get('notify_enabled'):
        lines.append("🔕 Уведомления отключены")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Вход в меню бюджета
# ---------------------------------------------------------------------------

async def budget_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывает меню раздела «Бюджет»."""
    user_id = update.effective_user.id
    log_event(logger, "budget_menu_opened", user_id=user_id)
    await update.message.reply_text(
        "💰 Управление бюджетом",
        reply_markup=_budget_menu_keyboard(),
    )


# ---------------------------------------------------------------------------
# Статус бюджета
# ---------------------------------------------------------------------------

async def budget_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывает текущий статус бюджета: установленный бюджет vs. траты."""
    user_id = update.effective_user.id
    project_id = context.user_data.get('active_project_id')

    if not await has_permission(user_id, project_id, Permission.VIEW_BUDGET):
        await update.message.reply_text(
            "❌ У вас нет прав для просмотра бюджета.",
            reply_markup=_budget_menu_keyboard(),
        )
        return

    now = datetime.datetime.now()
    month, year = now.month, now.year

    budget = await budgets_utils.get_or_inherit_budget(user_id, month, year, project_id)

    if budget is None:
        await update.message.reply_text(
            "ℹ️ Бюджет на текущий месяц не установлен.\n"
            "Нажмите «💰 Установить бюджет», чтобы задать лимит.",
            reply_markup=_budget_menu_keyboard(),
        )
        return

    expenses = await excel.get_month_expenses(user_id, month, year, project_id)
    spending = float(expenses.get('total', 0)) if expenses else 0.0

    text = _format_budget_status_text(budget, spending, month, year)
    await update.message.reply_text(text, reply_markup=_budget_menu_keyboard())
    log_event(logger, "budget_status_shown", user_id=user_id, month=month, year=year)


# ---------------------------------------------------------------------------
# Диалог: установить бюджет
# ---------------------------------------------------------------------------

async def set_budget_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Начало диалога установки бюджета."""
    user_id = update.effective_user.id
    project_id = context.user_data.get('active_project_id')

    if not await has_permission(user_id, project_id, Permission.SET_BUDGET):
        await update.message.reply_text(
            "❌ У вас нет прав для установки бюджета.\n"
            "Только владелец или редактор проекта может изменять бюджет.",
            reply_markup=_budget_menu_keyboard(),
        )
        return ConversationHandler.END

    now = datetime.datetime.now()
    from utils.helpers import get_month_name
    month_name = get_month_name(now.month)

    # Показываем текущий бюджет, если есть
    existing = await budgets_utils.get_budget(user_id, now.month, now.year, project_id)
    hint = ""
    if existing:
        hint = f"\n\nТекущий бюджет: {_fmt_amount(existing['amount'])}"

    await update.message.reply_text(
        f"💰 Введите сумму бюджета на {month_name} {now.year}:{hint}",
        reply_markup=ReplyKeyboardMarkup([["Отмена"]], resize_keyboard=True),
    )
    return ENTERING_AMOUNT


async def set_budget_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обрабатывает введённую сумму бюджета."""
    text = update.message.text.strip()
    if text == "Отмена":
        return await _cancel_set(update, context)

    try:
        amount = float(text.replace(",", ".").replace("\u202f", "").replace("\u00a0", ""))
        if amount <= 0:
            raise ValueError("Amount must be positive")
    except ValueError:
        await update.message.reply_text(
            "❌ Введите корректное число, например: 50000",
            reply_markup=ReplyKeyboardMarkup([["Отмена"]], resize_keyboard=True),
        )
        return ENTERING_AMOUNT

    context.user_data['budget_amount'] = amount

    await update.message.reply_text(
        f"✅ Сумма бюджета: {_fmt_amount(amount)}\n\n"
        "Хотите получать уведомление при приближении к лимиту?",
        reply_markup=ReplyKeyboardMarkup([["Да", "Нет"], ["Отмена"]], resize_keyboard=True),
    )
    return ASKING_NOTIFY


async def set_budget_notify_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обрабатывает выбор «настроить уведомления» да/нет."""
    text = update.message.text.strip()
    if text == "Отмена":
        return await _cancel_set(update, context)

    user_id = update.effective_user.id
    project_id = context.user_data.get('active_project_id')
    amount = context.user_data.get('budget_amount', 0.0)
    now = datetime.datetime.now()

    if text == "Да":
        await update.message.reply_text(
            f"Введите сумму, при которой отправлять уведомление.\n"
            f"Например: если бюджет {_fmt_amount(amount)}, "
            f"введите {_fmt_amount(amount * 0.9)} для уведомления при 90% использования.",
            reply_markup=ReplyKeyboardMarkup([["Отмена"]], resize_keyboard=True),
        )
        return ENTERING_THRESHOLD

    # «Нет» — сохраняем бюджет без уведомлений
    result = await budgets_utils.set_budget(user_id, now.month, now.year, amount, project_id)
    if result:
        # Явно отключаем уведомления — set_budget() не трогает notify_enabled,
        # поэтому если раньше было notify_enabled=TRUE, оно бы осталось включённым.
        await budgets_utils.disable_notification(user_id, now.month, now.year, project_id)
        from utils.helpers import get_month_name
        await update.message.reply_text(
            f"✅ Бюджет на {get_month_name(now.month)} {now.year} установлен: {_fmt_amount(amount)}\n"
            f"🔕 Уведомления отключены.",
            reply_markup=_budget_menu_keyboard(),
        )
        log_event(logger, "budget_set", user_id=user_id, amount=amount,
                  month=now.month, year=now.year, notify=False)
    else:
        await update.message.reply_text(
            "❌ Ошибка при сохранении бюджета.",
            reply_markup=_budget_menu_keyboard(),
        )
    context.user_data.pop('budget_amount', None)
    return ConversationHandler.END


async def set_budget_threshold(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обрабатывает введённый порог уведомления."""
    text = update.message.text.strip()
    if text == "Отмена":
        return await _cancel_set(update, context)

    amount = context.user_data.get('budget_amount', 0.0)

    try:
        threshold = float(text.replace(",", ".").replace("\u202f", "").replace("\u00a0", ""))
        if threshold <= 0:
            raise ValueError
        if threshold > amount:
            await update.message.reply_text(
                f"❌ Порог не может быть больше бюджета ({_fmt_amount(amount)}).\n"
                "Введите корректное значение:",
                reply_markup=ReplyKeyboardMarkup([["Отмена"]], resize_keyboard=True),
            )
            return ENTERING_THRESHOLD
    except ValueError:
        await update.message.reply_text(
            "❌ Введите корректное число:",
            reply_markup=ReplyKeyboardMarkup([["Отмена"]], resize_keyboard=True),
        )
        return ENTERING_THRESHOLD

    user_id = update.effective_user.id
    project_id = context.user_data.get('active_project_id')
    now = datetime.datetime.now()

    # Сохраняем бюджет и порог
    budget_result = await budgets_utils.set_budget(
        user_id, now.month, now.year, amount, project_id
    )
    notify_result = None
    if budget_result:
        notify_result = await budgets_utils.set_notification(
            user_id, now.month, now.year, threshold, project_id
        )

    if budget_result and notify_result:
        from utils.helpers import get_month_name
        await update.message.reply_text(
            f"✅ Бюджет установлен!\n\n"
            f"💰 Бюджет: {_fmt_amount(amount)}\n"
            f"🔔 Уведомление при: {_fmt_amount(threshold)}",
            reply_markup=_budget_menu_keyboard(),
        )
        log_event(logger, "budget_set", user_id=user_id, amount=amount,
                  threshold=threshold, month=now.month, year=now.year, notify=True)
    else:
        await update.message.reply_text(
            "❌ Ошибка при сохранении бюджета.",
            reply_markup=_budget_menu_keyboard(),
        )

    context.user_data.pop('budget_amount', None)
    return ConversationHandler.END


async def _cancel_set(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.pop('budget_amount', None)
    await update.message.reply_text(
        "Установка бюджета отменена.",
        reply_markup=_budget_menu_keyboard(),
    )
    return ConversationHandler.END


# ---------------------------------------------------------------------------
# Диалог: настроить уведомление
# ---------------------------------------------------------------------------

async def edit_notification_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Начало диалога изменения порога уведомления."""
    user_id = update.effective_user.id
    project_id = context.user_data.get('active_project_id')

    if not await has_permission(user_id, project_id, Permission.SET_BUDGET):
        await update.message.reply_text(
            "❌ У вас нет прав для настройки уведомлений.",
            reply_markup=_budget_menu_keyboard(),
        )
        return ConversationHandler.END

    now = datetime.datetime.now()
    budget = await budgets_utils.get_or_inherit_budget(user_id, now.month, now.year, project_id)

    if budget is None:
        await update.message.reply_text(
            "ℹ️ Сначала установите бюджет (кнопка «💰 Установить бюджет»).",
            reply_markup=_budget_menu_keyboard(),
        )
        return ConversationHandler.END

    current = budget.get('notify_threshold')
    hint = f"Текущий порог: {_fmt_amount(current)}\n\n" if current else ""
    await update.message.reply_text(
        f"🔔 Настройка уведомления о бюджете\n\n"
        f"💰 Бюджет: {_fmt_amount(budget['amount'])}\n"
        f"{hint}"
        f"Введите новый порог уведомления:",
        reply_markup=ReplyKeyboardMarkup([["Отмена"]], resize_keyboard=True),
    )
    return EDITING_THRESHOLD


async def edit_notification_threshold(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обрабатывает новый порог уведомления."""
    text = update.message.text.strip()
    if text == "Отмена":
        await update.message.reply_text(
            "Изменение уведомления отменено.",
            reply_markup=_budget_menu_keyboard(),
        )
        return ConversationHandler.END

    user_id = update.effective_user.id
    project_id = context.user_data.get('active_project_id')
    now = datetime.datetime.now()

    budget = await budgets_utils.get_or_inherit_budget(user_id, now.month, now.year, project_id)
    if budget is None:
        await update.message.reply_text(
            "❌ Бюджет не найден.",
            reply_markup=_budget_menu_keyboard(),
        )
        return ConversationHandler.END

    try:
        threshold = float(text.replace(",", ".").replace("\u202f", "").replace("\u00a0", ""))
        if threshold <= 0 or threshold > budget['amount']:
            raise ValueError
    except ValueError:
        await update.message.reply_text(
            f"❌ Введите число от 1 до {_fmt_amount(budget['amount'])}:",
            reply_markup=ReplyKeyboardMarkup([["Отмена"]], resize_keyboard=True),
        )
        return EDITING_THRESHOLD

    result = await budgets_utils.set_notification(
        user_id, now.month, now.year, threshold, project_id
    )
    if result:
        await update.message.reply_text(
            f"✅ Порог уведомления изменён: {_fmt_amount(threshold)}",
            reply_markup=_budget_menu_keyboard(),
        )
        log_event(logger, "notification_updated", user_id=user_id, threshold=threshold)
    else:
        await update.message.reply_text(
            "❌ Ошибка при обновлении уведомления.",
            reply_markup=_budget_menu_keyboard(),
        )
    return ConversationHandler.END


# ---------------------------------------------------------------------------
# Отключить уведомления
# ---------------------------------------------------------------------------

async def disable_notifications_handler(update: Update,
                                        context: ContextTypes.DEFAULT_TYPE) -> None:
    """Отключает уведомления о бюджете."""
    user_id = update.effective_user.id
    project_id = context.user_data.get('active_project_id')

    if not await has_permission(user_id, project_id, Permission.SET_BUDGET):
        await update.message.reply_text(
            "❌ У вас нет прав для изменения уведомлений.",
            reply_markup=_budget_menu_keyboard(),
        )
        return

    now = datetime.datetime.now()
    result = await budgets_utils.disable_notification(user_id, now.month, now.year, project_id)
    if result:
        await update.message.reply_text(
            "🔕 Уведомления о бюджете отключены.",
            reply_markup=_budget_menu_keyboard(),
        )
        log_event(logger, "notifications_disabled", user_id=user_id)
    else:
        await update.message.reply_text(
            "ℹ️ Бюджет не установлен или уведомления уже отключены.",
            reply_markup=_budget_menu_keyboard(),
        )


# ---------------------------------------------------------------------------
# Регистрация обработчиков
# ---------------------------------------------------------------------------

def register_budget_handlers(application) -> None:
    """Регистрирует все обработчики бюджета."""

    # ConversationHandler: установка бюджета
    set_budget_conv = ConversationHandler(
        entry_points=[
            MessageHandler(
                filters.Regex(_budget_menu_button_regex("set")),
                set_budget_start,
            ),
        ],
        states={
            ENTERING_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_budget_amount)],
            ASKING_NOTIFY:   [MessageHandler(filters.TEXT & ~filters.COMMAND, set_budget_notify_choice)],
            ENTERING_THRESHOLD: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_budget_threshold)],
        },
        fallbacks=[
            MessageHandler(filters.Regex(r"^Отмена$"), _cancel_set),
            MessageHandler(filters.Regex(main_menu_button_regex("main_menu")), _cancel_set),
        ],
        name="set_budget_conversation",
        persistent=False,
    )

    # ConversationHandler: редактирование уведомления
    edit_notify_conv = ConversationHandler(
        entry_points=[
            MessageHandler(
                filters.Regex(_budget_menu_button_regex("edit_notify")),
                edit_notification_start,
            ),
        ],
        states={
            EDITING_THRESHOLD: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_notification_threshold)],
        },
        fallbacks=[
            MessageHandler(filters.Regex(r"^Отмена$"), lambda u, c: ConversationHandler.END),
            MessageHandler(filters.Regex(main_menu_button_regex("main_menu")),
                           lambda u, c: ConversationHandler.END),
        ],
        name="edit_notification_conversation",
        persistent=False,
    )

    # Регистрируем ConversationHandler-ы ПЕРЕД простыми MessageHandler-ами
    application.add_handler(set_budget_conv)
    application.add_handler(edit_notify_conv)

    # Вход в меню бюджета
    application.add_handler(
        MessageHandler(filters.Regex(main_menu_button_regex("budget")), budget_menu)
    )

    # Статус бюджета
    application.add_handler(
        MessageHandler(filters.Regex(_budget_menu_button_regex("status")), budget_status)
    )

    # Отключить уведомления
    application.add_handler(
        MessageHandler(
            filters.Regex(_budget_menu_button_regex("disable_notify")),
            disable_notifications_handler,
        )
    )

    # Кнопка «⬅️ Главное меню» внутри бюджет-меню
    application.add_handler(
        MessageHandler(
            filters.Regex(_budget_menu_button_regex("back")),
            lambda u, c: u.message.reply_text(
                "Главное меню", reply_markup=get_main_menu_keyboard()
            ),
        )
    )
