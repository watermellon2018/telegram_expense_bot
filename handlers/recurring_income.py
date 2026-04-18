"""Обработчики постоянных доходов."""

import datetime
from typing import Tuple

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler, MessageHandler, CallbackQueryHandler, CommandHandler, filters

import config
from utils import income_categories
from utils import recurring_incomes
from utils import recurring as recurring_utils
from utils.helpers import income_menu_button_regex, get_main_menu_keyboard

(
    REC_ENTERING_AMOUNT,
    REC_CHOOSING_CATEGORY,
    REC_ENTERING_COMMENT,
    REC_CHOOSING_FREQUENCY,
    REC_ENTERING_CUSTOM_FREQUENCY,
) = range(5)


def _format_next_run(next_run_at) -> str:
    if not next_run_at:
        return "—"
    if hasattr(next_run_at, "strftime"):
        return next_run_at.strftime("%d.%m.%Y")
    return str(next_run_at)


def _build_rules_message_and_keyboard(rules: list) -> Tuple[str, InlineKeyboardMarkup]:
    if not rules:
        text = "🔁 *Постоянные доходы*\n\nУ вас пока нет правил постоянного дохода."
        keyboard = [[InlineKeyboardButton("➕ Добавить постоянный доход", callback_data="rin_add")]]
        return text, InlineKeyboardMarkup(keyboard)

    lines = ["🔁 *Постоянные доходы*\n"]
    keyboard = []
    for idx, rule in enumerate(rules, 1):
        status_icon = "✅" if rule["status"] == "active" else "⏸"
        freq_text = recurring_utils.format_frequency(rule)
        display_name = rule.get("comment") or rule.get("category_name")
        lines.append(
            f"{idx}. {display_name} — {rule['amount']}\n"
            f"   📅 {freq_text} | {status_icon}\n"
            f"   Следующее: {_format_next_run(rule.get('next_run_at'))}"
        )

        rule_id = rule["id"]
        row = [InlineKeyboardButton(f"{idx}", callback_data=f"rin_label_{rule_id}")]
        if rule["status"] == "active":
            row.append(InlineKeyboardButton("⏸ Пауза", callback_data=f"rin_pause_{rule_id}"))
        else:
            row.append(InlineKeyboardButton("▶️ Возобновить", callback_data=f"rin_resume_{rule_id}"))
        row.append(InlineKeyboardButton("🗑 Удалить", callback_data=f"rin_delete_{rule_id}"))
        keyboard.append(row)

    keyboard.append([InlineKeyboardButton("➕ Добавить постоянный доход", callback_data="rin_add")])
    return "\n".join(lines), InlineKeyboardMarkup(keyboard)


def _build_category_keyboard(cats: list) -> InlineKeyboardMarkup:
    keyboard = []
    row = []
    for idx, cat in enumerate(cats):
        emoji = config.DEFAULT_INCOME_CATEGORIES.get(cat["name"], "💵")
        row.append(InlineKeyboardButton(f"{emoji} {cat['name']}", callback_data=f"rin_cat_{cat['income_category_id']}"))
        if len(row) == 2 or idx == len(cats) - 1:
            keyboard.append(row)
            row = []
    return InlineKeyboardMarkup(keyboard)


def _build_frequency_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📆 Каждый день", callback_data="rin_freq_daily"),
            InlineKeyboardButton("📅 Каждую неделю", callback_data="rin_freq_weekly"),
        ],
        [
            InlineKeyboardButton("🗓 Каждый месяц", callback_data="rin_freq_monthly"),
            InlineKeyboardButton("✏️ Другое...", callback_data="rin_freq_custom"),
        ],
    ])


async def recurring_income_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывает список правил постоянных доходов."""
    user_id = str(update.effective_user.id)
    project_id = context.user_data.get("active_project_id")

    rules = await recurring_incomes.get_rules_for_user(user_id, project_id)
    text, keyboard = _build_rules_message_and_keyboard(rules)
    await update.message.reply_text(text, reply_markup=keyboard, parse_mode="Markdown")


async def rin_add_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    context.user_data["rin_user_id"] = str(update.effective_user.id)
    for key in ["rin_amount", "rin_category_id", "rin_category_name", "rin_comment", "rin_freq_params"]:
        context.user_data.pop(key, None)

    await query.edit_message_text("➕ *Добавить постоянный доход*\n\nВведите сумму:", parse_mode="Markdown")
    return REC_ENTERING_AMOUNT


async def rin_handle_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        amount = float(update.message.text.replace(",", "."))
        if amount <= 0:
            await update.message.reply_text("❌ Сумма должна быть больше нуля.")
            return REC_ENTERING_AMOUNT
    except ValueError:
        await update.message.reply_text("❌ Введите число, например 5000")
        return REC_ENTERING_AMOUNT

    context.user_data["rin_amount"] = amount

    user_id = update.effective_user.id
    project_id = context.user_data.get("active_project_id")
    cats = await income_categories.get_income_categories_for_user_project(user_id, project_id)
    if not cats:
        await update.message.reply_text("❌ Нет категорий доходов.", reply_markup=get_main_menu_keyboard())
        return ConversationHandler.END

    await update.message.reply_text(
        f"💰 Сумма: *{amount}*\n\nВыберите категорию:",
        reply_markup=_build_category_keyboard(cats),
        parse_mode="Markdown",
    )
    return REC_CHOOSING_CATEGORY


async def rin_handle_category(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    try:
        category_id = int(query.data.split("_")[2])
    except (ValueError, IndexError):
        await query.edit_message_text("❌ Ошибка выбора категории.")
        return ConversationHandler.END

    user_id = update.effective_user.id
    category = await income_categories.get_income_category_by_id(user_id, category_id)
    if not category:
        await query.edit_message_text("❌ Категория не найдена.")
        return ConversationHandler.END

    context.user_data["rin_category_id"] = category_id
    context.user_data["rin_category_name"] = category["name"]

    await query.edit_message_text(
        f"💰 Сумма: *{context.user_data.get('rin_amount')}*\n"
        f"Категория: *{category['name']}*\n\n"
        "Введите комментарий (обязательный):",
        parse_mode="Markdown",
    )
    return REC_ENTERING_COMMENT


async def rin_handle_comment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    comment = update.message.text.strip()
    if not comment:
        await update.message.reply_text("❌ Комментарий обязателен.")
        return REC_ENTERING_COMMENT

    context.user_data["rin_comment"] = comment
    await update.message.reply_text(
        "Выберите частоту начисления:",
        reply_markup=_build_frequency_keyboard(),
    )
    return REC_CHOOSING_FREQUENCY


async def rin_handle_frequency_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    cb = query.data
    if cb == "rin_freq_custom":
        await query.edit_message_text(
            "Введите частоту в свободной форме:\n"
            "• каждые 3 дня\n"
            "• каждые 2 недели\n"
            "• каждый месяц\n"
            "• 15 числа\n"
            "• последний день месяца"
        )
        return REC_ENTERING_CUSTOM_FREQUENCY

    freq_map = {
        "rin_freq_daily": {"frequency_type": "daily"},
        "rin_freq_weekly": {"frequency_type": "weekly"},
        "rin_freq_monthly": {"frequency_type": "monthly"},
    }
    freq_params = freq_map.get(cb)
    if not freq_params:
        await query.edit_message_text("❌ Неизвестная частота.")
        return REC_CHOOSING_FREQUENCY

    context.user_data["rin_freq_params"] = freq_params
    return await _finalize_rule(query, context)


async def rin_handle_custom_frequency(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    from utils.pattern_detector import parse_custom_frequency

    freq_params = parse_custom_frequency(update.message.text.strip())
    if freq_params is None:
        await update.message.reply_text(
            "❌ Не удалось распознать частоту. Пример: 'каждые 2 недели'."
        )
        return REC_ENTERING_CUSTOM_FREQUENCY

    context.user_data["rin_freq_params"] = freq_params
    return await _finalize_rule(update.message, context)


async def _finalize_rule(message_or_query, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = context.user_data.get("rin_user_id", "")
    amount = context.user_data.get("rin_amount")
    category_id = context.user_data.get("rin_category_id")
    comment = context.user_data.get("rin_comment", "")
    project_id = context.user_data.get("active_project_id")
    freq_params = context.user_data.get("rin_freq_params", {})

    rule_id = await recurring_incomes.create_rule(
        user_id=user_id,
        amount=amount,
        income_category_id=category_id,
        comment=comment,
        project_id=project_id,
        frequency_type=freq_params.get("frequency_type", "monthly"),
        interval_value=freq_params.get("interval_value"),
        weekday=freq_params.get("weekday"),
        day_of_month=freq_params.get("day_of_month"),
        is_last_day_of_month=freq_params.get("is_last_day_of_month", False),
        start_date=datetime.date.today(),
    )

    for key in ["rin_user_id", "rin_amount", "rin_category_id", "rin_category_name", "rin_comment", "rin_freq_params"]:
        context.user_data.pop(key, None)

    if not rule_id:
        text = "❌ Не удалось создать правило постоянного дохода."
    else:
        rule = await recurring_incomes.get_rule_by_id(rule_id, user_id)
        freq_text = recurring_utils.format_frequency(rule) if rule else "—"
        text = (
            "✅ Постоянный доход добавлен!\n"
            "Также создана фактическая запись дохода за сегодня.\n"
            f"💰 {amount} — {comment}\n"
            f"📅 {freq_text}\n"
            f"🗓 Следующее начисление: {_format_next_run(rule.get('next_run_at') if rule else None)}"
        )

    if hasattr(message_or_query, "edit_message_text"):
        await message_or_query.edit_message_text(text)
        await message_or_query.message.reply_text("Возврат в главное меню.", reply_markup=get_main_menu_keyboard())
    else:
        await message_or_query.reply_text(text, reply_markup=get_main_menu_keyboard())

    return ConversationHandler.END


async def rin_pause_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    rule_id = int(query.data.split("_")[2])
    user_id = str(update.effective_user.id)

    await recurring_incomes.pause_rule(rule_id, user_id)
    rules = await recurring_incomes.get_rules_for_user(user_id, context.user_data.get("active_project_id"))
    text, keyboard = _build_rules_message_and_keyboard(rules)
    await query.edit_message_text(text, reply_markup=keyboard, parse_mode="Markdown")


async def rin_resume_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    rule_id = int(query.data.split("_")[2])
    user_id = str(update.effective_user.id)

    await recurring_incomes.resume_rule(rule_id, user_id)
    rules = await recurring_incomes.get_rules_for_user(user_id, context.user_data.get("active_project_id"))
    text, keyboard = _build_rules_message_and_keyboard(rules)
    await query.edit_message_text(text, reply_markup=keyboard, parse_mode="Markdown")


async def rin_delete_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    rule_id = int(query.data.split("_")[2])
    user_id = str(update.effective_user.id)

    await recurring_incomes.delete_rule(rule_id, user_id)
    rules = await recurring_incomes.get_rules_for_user(user_id, context.user_data.get("active_project_id"))
    text, keyboard = _build_rules_message_and_keyboard(rules)
    await query.edit_message_text(text, reply_markup=keyboard, parse_mode="Markdown")


async def rin_label_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()


async def rin_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    for key in ["rin_user_id", "rin_amount", "rin_category_id", "rin_category_name", "rin_comment", "rin_freq_params"]:
        context.user_data.pop(key, None)
    from utils.helpers import cancel_conversation
    return await cancel_conversation(update, context, "Добавление постоянного дохода отменено.")


def register_recurring_income_handlers(application):
    application.add_handler(MessageHandler(filters.Regex(income_menu_button_regex("recurring")), recurring_income_menu))

    conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(rin_add_start, pattern=r"^rin_add$")],
        states={
            REC_ENTERING_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, rin_handle_amount)],
            REC_CHOOSING_CATEGORY: [CallbackQueryHandler(rin_handle_category, pattern=r"^rin_cat_\d+$")],
            REC_ENTERING_COMMENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, rin_handle_comment)],
            REC_CHOOSING_FREQUENCY: [CallbackQueryHandler(rin_handle_frequency_choice, pattern=r"^rin_freq_")],
            REC_ENTERING_CUSTOM_FREQUENCY: [MessageHandler(filters.TEXT & ~filters.COMMAND, rin_handle_custom_frequency)],
        },
        fallbacks=[CommandHandler("cancel", rin_cancel)],
        name="add_recurring_income_conversation",
        persistent=False,
    )
    application.add_handler(conv)

    application.add_handler(CallbackQueryHandler(rin_label_callback, pattern=r"^rin_label_\d+$"))
    application.add_handler(CallbackQueryHandler(rin_pause_callback, pattern=r"^rin_pause_\d+$"))
    application.add_handler(CallbackQueryHandler(rin_resume_callback, pattern=r"^rin_resume_\d+$"))
    application.add_handler(CallbackQueryHandler(rin_delete_callback, pattern=r"^rin_delete_\d+$"))
