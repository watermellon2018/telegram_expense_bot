"""Обработчики раздела теоретического кэшбэка."""

import datetime

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, Update
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from utils import cashback, helpers
from utils.helpers import (
    cashback_cards_menu_button_regex,
    cashback_categories_menu_button_regex,
    cashback_menu_button_regex,
    cashback_rules_menu_button_regex,
    main_menu_button_regex,
)
from utils.logger import get_logger, log_event

logger = get_logger("handlers.cashback")

CANCEL_INPUT_KEYBOARD = ReplyKeyboardMarkup([["❌ Отмена"]], resize_keyboard=True)

CB_CARD_EDIT_PREFIX = "cb_card_edit_"
CB_CARD_EDIT_ACTION_PREFIX = "cb_card_edit_action_"
CB_CARD_DELETE_PREFIX = "cb_card_delete_"
CB_CAT_DELETE_PREFIX = "cb_cat_del_"
CB_RULE_ADD_CARD_PREFIX = "cb_rule_add_card_"
CB_RULE_ADD_CAT_PREFIX = "cb_rule_add_cat_"
CB_RULE_EDIT_PREFIX = "cb_rule_edit_"
CB_RULE_DELETE_PREFIX = "cb_rule_del_"
CB_CANCEL = "cancel"

(
    CARD_ADD_NAME,
    CARD_EDIT_SELECT,
    CARD_EDIT_ACTION_SELECT,
    CARD_DELETE_SELECT,
    CATEGORY_ADD_NAME,
    CATEGORY_DELETE_SELECT,
    RULE_ADD_SELECT_CARD,
    RULE_ADD_SELECT_CATEGORY,
    RULE_ADD_ENTER_PERCENT,
    RULE_EDIT_SELECT,
    RULE_EDIT_ENTER_PERCENT,
    RULE_DELETE_SELECT,
) = range(12)


def _current_month_year() -> tuple[int, int]:
    now = datetime.datetime.now()
    return now.month, now.year


def _parse_month_year(args: list[str]) -> tuple[int, int]:
    month, year = _current_month_year()
    if len(args) >= 1:
        month = int(args[0])
    if len(args) >= 2:
        year = int(args[1])
    return month, year


def _parse_percent(text: str):
    try:
        value = float((text or "").strip().replace(",", "."))
    except ValueError:
        return None
    if value < 0 or value > 100:
        return None
    return value


def _format_cards(cards):
    if not cards:
        return "💳 У вас пока нет карт."

    lines = ["💳 Ваши карты:"]
    for card in cards:
        status = "✅ активна" if card["is_active"] else "⏸️ неактивна"
        lines.append(f"- {card['card_name']} ({status})")
    return "\n".join(lines)


def _format_categories(categories):
    if not categories:
        return "🗂️ Категории кэшбэка пока пусты."

    lines = ["🗂️ Категории кэшбэка:"]
    global_rows = [c for c in categories if c["is_global"]]
    user_rows = [c for c in categories if not c["is_global"]]

    if global_rows:
        lines.append("")
        lines.append("🌐 Базовые категории:")
        for row in global_rows:
            emoji = cashback.get_cashback_category_emoji(row["name"])
            lines.append(f"- {emoji} {row['name']}")

    if user_rows:
        lines.append("")
        lines.append("👤 Ваши категории:")
        for row in user_rows:
            emoji = cashback.get_cashback_category_emoji(row["name"])
            lines.append(f"- {emoji} {row['name']}")

    return "\n".join(lines)


def _format_rules(rules, month: int, year: int):
    if not rules:
        return f"🧾 На {month:02d}.{year} правил пока нет."

    lines = [f"🧾 Правила кэшбэка на {month:02d}.{year}:"]
    for rule in rules:
        emoji = cashback.get_cashback_category_emoji(rule["cashback_category_name"])
        lines.append(
            f"- 💳 {rule['card_name']} | {emoji} {rule['cashback_category_name']} | {float(rule['percent']):.2f}%"
        )
    return "\n".join(lines)


async def cashback_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    log_event(logger, "cashback_menu_opened", user_id=user_id)

    await cashback.ensure_global_cashback_categories_exist()
    await update.message.reply_text(
        "💳 Кэшбэк (MVP)\n\n"
        "Здесь отображается только теоретический кэшбэк.\n"
        f"{cashback.POTENTIAL_CASHBACK_DISCLAIMER}\n\n"
        "Выберите раздел:",
        reply_markup=helpers.get_cashback_menu_keyboard(),
    )


async def cashback_back(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "⬅️ Возврат в главное меню",
        reply_markup=helpers.get_main_menu_keyboard(),
    )


async def cashback_cards_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    cards = await cashback.list_user_cards(user_id, include_inactive=True)
    await update.message.reply_text(
        _format_cards(cards),
        reply_markup=helpers.get_cashback_cards_menu_keyboard(),
    )


async def cashback_rules_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    month, year = _current_month_year()
    rules = await cashback.list_user_cashback_rules(user_id, year=year, month=month)
    await update.message.reply_text(
        _format_rules(rules, month, year),
        reply_markup=helpers.get_cashback_rules_menu_keyboard(),
    )


async def cashback_categories_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    categories = await cashback.list_cashback_categories(user_id)
    await update.message.reply_text(
        _format_categories(categories),
        reply_markup=helpers.get_cashback_categories_menu_keyboard(),
    )


async def cashback_cards_back(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "⬅️ Раздел «Кэшбэк»",
        reply_markup=helpers.get_cashback_menu_keyboard(),
    )


async def cashback_rules_back(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "⬅️ Раздел «Кэшбэк»",
        reply_markup=helpers.get_cashback_menu_keyboard(),
    )


async def cashback_categories_back(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "⬅️ Раздел «Кэшбэк»",
        reply_markup=helpers.get_cashback_menu_keyboard(),
    )


async def cancel_to_cards_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await cashback_cards_back(update, context)
    return ConversationHandler.END


async def cancel_to_rules_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await cashback_rules_back(update, context)
    return ConversationHandler.END


async def cancel_to_categories_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await cashback_categories_back(update, context)
    return ConversationHandler.END


async def cashback_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    project_id = context.user_data.get("active_project_id")
    try:
        args = getattr(context, "args", None) or []
        month, year = _parse_month_year(args)
    except (ValueError, TypeError):
        await update.message.reply_text("❌ Неверный формат. Используйте: /cashback_stats [month] [year]")
        return

    if not (1 <= month <= 12):
        await update.message.reply_text("❌ Месяц должен быть от 1 до 12.")
        return

    summary = await cashback.calculate_potential_cashback_for_period(
        user_id=user_id,
        year=year,
        month=month,
        project_id=project_id,
    )
    await update.message.reply_text(
        cashback.format_cashback_summary(
            summary,
            title=f"📈 Теоретический кэшбэк за {month:02d}.{year}",
            include_effective_spent=False,
        ),
        reply_markup=helpers.get_cashback_menu_keyboard(),
    )


async def cashback_cards_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await cashback_cards_menu(update, context)


async def cashback_categories_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await cashback_categories_menu(update, context)

# ---------------------------------------------------------------------------
# Cards
# ---------------------------------------------------------------------------

async def cashback_card_add_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Введите название новой карты:", reply_markup=CANCEL_INPUT_KEYBOARD)
    return CARD_ADD_NAME


async def cashback_card_add_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = (update.message.text or "").strip()
    if text == "❌ Отмена":
        await update.message.reply_text(
            "❌ Добавление карты отменено.",
            reply_markup=helpers.get_cashback_cards_menu_keyboard(),
        )
        return ConversationHandler.END

    user_id = update.effective_user.id
    result = await cashback.create_user_card(user_id, text)
    if result["success"]:
        await update.message.reply_text(
            f"✅ Карта добавлена: {result['card_name']}",
            reply_markup=helpers.get_cashback_cards_menu_keyboard(),
        )
        return ConversationHandler.END

    await update.message.reply_text(f"❌ {result['message']}")
    return CARD_ADD_NAME


async def cashback_card_edit_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    cards = await cashback.list_user_cards(user_id, include_inactive=True)
    if not cards:
        await update.message.reply_text(
            "💳 У вас пока нет карт.",
            reply_markup=helpers.get_cashback_cards_menu_keyboard(),
        )
        return ConversationHandler.END

    keyboard = []
    for card in cards:
        status = "✅" if card["is_active"] else "⏸️"
        keyboard.append([
            InlineKeyboardButton(
                f"{status} {card['card_name']}",
                callback_data=f"{CB_CARD_EDIT_PREFIX}{card['id']}",
            )
        ])
    keyboard.append([InlineKeyboardButton("❌ Отмена", callback_data=f"{CB_CARD_EDIT_PREFIX}{CB_CANCEL}")])

    await update.message.reply_text(
        "Выберите карту для редактирования:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return CARD_EDIT_SELECT


async def cashback_card_edit_select(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    data = query.data[len(CB_CARD_EDIT_PREFIX):]
    if data == CB_CANCEL:
        await query.edit_message_text("❌ Редактирование карты отменено.")
        await query.message.reply_text("Выберите действие:", reply_markup=helpers.get_cashback_cards_menu_keyboard())
        return ConversationHandler.END

    user_id = update.effective_user.id
    cards = await cashback.list_user_cards(user_id, include_inactive=True)
    selected = next((row for row in cards if row["id"] == int(data)), None)
    if not selected:
        await query.edit_message_text("❌ Карта не найдена.")
        await query.message.reply_text("Выберите действие:", reply_markup=helpers.get_cashback_cards_menu_keyboard())
        return ConversationHandler.END

    context.user_data["cashback_edit_card_id"] = selected["id"]
    context.user_data["cashback_edit_card_name"] = selected["card_name"]
    context.user_data["cashback_edit_card_is_active"] = selected["is_active"]

    if selected["is_active"]:
        action_button = InlineKeyboardButton(
            "⏸️ Деактивировать",
            callback_data=f"{CB_CARD_EDIT_ACTION_PREFIX}deactivate",
        )
        action_text = "Карта сейчас активна. Что сделать?"
    else:
        action_button = InlineKeyboardButton(
            "✅ Активировать",
            callback_data=f"{CB_CARD_EDIT_ACTION_PREFIX}activate",
        )
        action_text = "Карта сейчас на паузе. Что сделать?"

    keyboard = [
        [action_button],
        [InlineKeyboardButton("❌ Отмена", callback_data=f"{CB_CARD_EDIT_ACTION_PREFIX}{CB_CANCEL}")],
    ]
    await query.edit_message_text(action_text, reply_markup=InlineKeyboardMarkup(keyboard))
    return CARD_EDIT_ACTION_SELECT


async def cashback_card_edit_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    action = query.data[len(CB_CARD_EDIT_ACTION_PREFIX):]
    if action == CB_CANCEL:
        context.user_data.pop("cashback_edit_card_id", None)
        context.user_data.pop("cashback_edit_card_name", None)
        context.user_data.pop("cashback_edit_card_is_active", None)
        await query.edit_message_text("❌ Редактирование карты отменено.")
        await query.message.reply_text("Выберите действие:", reply_markup=helpers.get_cashback_cards_menu_keyboard())
        return ConversationHandler.END

    card_id = context.user_data.pop("cashback_edit_card_id", None)
    context.user_data.pop("cashback_edit_card_name", None)
    context.user_data.pop("cashback_edit_card_is_active", None)
    if not card_id:
        await query.edit_message_text("❌ Ошибка контекста. Повторите действие.")
        await query.message.reply_text("Выберите действие:", reply_markup=helpers.get_cashback_cards_menu_keyboard())
        return ConversationHandler.END

    user_id = update.effective_user.id
    if action == "activate":
        result = await cashback.activate_user_card(user_id, int(card_id))
        success_text = f"✅ Карта активирована: {result.get('card_name', '')}"
    elif action == "deactivate":
        result = await cashback.deactivate_user_card(user_id, int(card_id))
        success_text = f"✅ Карта деактивирована: {result.get('card_name', '')}"
    else:
        await query.edit_message_text("❌ Неверная команда.")
        await query.message.reply_text("Выберите действие:", reply_markup=helpers.get_cashback_cards_menu_keyboard())
        return ConversationHandler.END

    if result["success"]:
        await query.edit_message_text(success_text)
    else:
        await query.edit_message_text(f"❌ {result['message']}")
    await query.message.reply_text("Выберите действие:", reply_markup=helpers.get_cashback_cards_menu_keyboard())
    return ConversationHandler.END


async def cashback_card_delete_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    cards = await cashback.list_user_cards(user_id, include_inactive=True)
    if not cards:
        await update.message.reply_text(
            "💳 У вас пока нет карт.",
            reply_markup=helpers.get_cashback_cards_menu_keyboard(),
        )
        return ConversationHandler.END

    keyboard = []
    for card in cards:
        status = "✅" if card["is_active"] else "⏸️"
        keyboard.append([
            InlineKeyboardButton(
                f"{status} {card['card_name']}",
                callback_data=f"{CB_CARD_DELETE_PREFIX}{card['id']}",
            )
        ])
    keyboard.append([InlineKeyboardButton("❌ Отмена", callback_data=f"{CB_CARD_DELETE_PREFIX}{CB_CANCEL}")])

    await update.message.reply_text(
        "Выберите карту для удаления:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return CARD_DELETE_SELECT


async def cashback_card_delete_select(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    data = query.data[len(CB_CARD_DELETE_PREFIX):]
    if data == CB_CANCEL:
        await query.edit_message_text("❌ Удаление карты отменено.")
        await query.message.reply_text("Выберите действие:", reply_markup=helpers.get_cashback_cards_menu_keyboard())
        return ConversationHandler.END

    user_id = update.effective_user.id
    result = await cashback.hard_delete_user_card(user_id, int(data))
    if result["success"]:
        await query.edit_message_text(f"✅ Карта удалена: {result['card_name']}")
    else:
        await query.edit_message_text(f"❌ {result['message']}")
    await query.message.reply_text("Выберите действие:", reply_markup=helpers.get_cashback_cards_menu_keyboard())
    return ConversationHandler.END


# ---------------------------------------------------------------------------
# Categories
# ---------------------------------------------------------------------------

async def cashback_category_add_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Введите название новой категории кэшбэка:", reply_markup=CANCEL_INPUT_KEYBOARD)
    return CATEGORY_ADD_NAME


async def cashback_category_add_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = (update.message.text or "").strip()
    if text == "❌ Отмена":
        await update.message.reply_text(
            "❌ Добавление категории отменено.",
            reply_markup=helpers.get_cashback_categories_menu_keyboard(),
        )
        return ConversationHandler.END

    user_id = update.effective_user.id
    result = await cashback.create_custom_cashback_category(user_id, text)
    if result["success"]:
        await update.message.reply_text(
            f"✅ Категория создана: {result['name']}",
            reply_markup=helpers.get_cashback_categories_menu_keyboard(),
        )
        return ConversationHandler.END

    await update.message.reply_text(f"❌ {result['message']}")
    return CATEGORY_ADD_NAME


async def cashback_category_delete_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    categories = await cashback.list_cashback_categories(user_id)
    custom_categories = [row for row in categories if not row["is_global"]]

    if not custom_categories:
        await update.message.reply_text(
            "🗑️ Нет пользовательских категорий для удаления.",
            reply_markup=helpers.get_cashback_categories_menu_keyboard(),
        )
        return ConversationHandler.END

    keyboard = []
    for row in custom_categories:
        emoji = cashback.get_cashback_category_emoji(row["name"])
        keyboard.append([InlineKeyboardButton(f"{emoji} {row['name']}", callback_data=f"{CB_CAT_DELETE_PREFIX}{row['id']}")])
    keyboard.append([InlineKeyboardButton("❌ Отмена", callback_data=f"{CB_CAT_DELETE_PREFIX}{CB_CANCEL}")])

    await update.message.reply_text(
        "Выберите пользовательскую категорию для удаления:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return CATEGORY_DELETE_SELECT


async def cashback_category_delete_select(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    data = query.data[len(CB_CAT_DELETE_PREFIX):]
    if data == CB_CANCEL:
        await query.edit_message_text("❌ Удаление категории отменено.")
        await query.message.reply_text("Выберите действие:", reply_markup=helpers.get_cashback_categories_menu_keyboard())
        return ConversationHandler.END

    user_id = update.effective_user.id
    result = await cashback.delete_custom_cashback_category(user_id, int(data))
    if result["success"]:
        emoji = cashback.get_cashback_category_emoji(result["name"])
        await query.edit_message_text(f"✅ Категория удалена: {emoji} {result['name']}")
    else:
        await query.edit_message_text(f"❌ {result['message']}")

    await query.message.reply_text("Выберите действие:", reply_markup=helpers.get_cashback_categories_menu_keyboard())
    return ConversationHandler.END


# ---------------------------------------------------------------------------
# Rules
# ---------------------------------------------------------------------------

async def cashback_rule_add_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    cards = await cashback.list_user_cards(user_id, include_inactive=False)
    if not cards:
        await update.message.reply_text(
            "❌ Нет активных карт. Сначала добавьте карту.",
            reply_markup=helpers.get_cashback_rules_menu_keyboard(),
        )
        return ConversationHandler.END

    keyboard = []
    for card in cards:
        keyboard.append([InlineKeyboardButton(f"💳 {card['card_name']}", callback_data=f"{CB_RULE_ADD_CARD_PREFIX}{card['id']}")])
    keyboard.append([InlineKeyboardButton("❌ Отмена", callback_data=f"{CB_RULE_ADD_CARD_PREFIX}{CB_CANCEL}")])

    await update.message.reply_text("Выберите карту:", reply_markup=InlineKeyboardMarkup(keyboard))
    return RULE_ADD_SELECT_CARD


async def cashback_rule_add_select_card(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    data = query.data[len(CB_RULE_ADD_CARD_PREFIX):]
    if data == CB_CANCEL:
        await query.edit_message_text("❌ Добавление кэшбека отменено.")
        await query.message.reply_text("Выберите действие:", reply_markup=helpers.get_cashback_rules_menu_keyboard())
        return ConversationHandler.END

    context.user_data["cashback_rule_add_card_id"] = int(data)

    user_id = update.effective_user.id
    categories = await cashback.list_cashback_categories(user_id)
    keyboard = []
    for row in categories:
        emoji = cashback.get_cashback_category_emoji(row["name"])
        keyboard.append([InlineKeyboardButton(f"{emoji} {row['name']}", callback_data=f"{CB_RULE_ADD_CAT_PREFIX}{row['id']}")])
    keyboard.append([InlineKeyboardButton("❌ Отмена", callback_data=f"{CB_RULE_ADD_CAT_PREFIX}{CB_CANCEL}")])

    await query.edit_message_text("Выберите cashback-категорию:", reply_markup=InlineKeyboardMarkup(keyboard))
    return RULE_ADD_SELECT_CATEGORY


async def cashback_rule_add_select_category(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    data = query.data[len(CB_RULE_ADD_CAT_PREFIX):]
    if data == CB_CANCEL:
        context.user_data.pop("cashback_rule_add_card_id", None)
        await query.edit_message_text("❌ Добавление кэшбека отменено.")
        await query.message.reply_text("Выберите действие:", reply_markup=helpers.get_cashback_rules_menu_keyboard())
        return ConversationHandler.END

    context.user_data["cashback_rule_add_category_id"] = int(data)
    await query.edit_message_text("Введите процент кэшбэка (0..100):")
    await query.message.reply_text("Ожидаю процент:", reply_markup=CANCEL_INPUT_KEYBOARD)
    return RULE_ADD_ENTER_PERCENT


async def cashback_rule_add_enter_percent(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = (update.message.text or "").strip()
    if text == "❌ Отмена":
        context.user_data.pop("cashback_rule_add_card_id", None)
        context.user_data.pop("cashback_rule_add_category_id", None)
        await update.message.reply_text(
            "❌ Добавление кэшбека отменено.",
            reply_markup=helpers.get_cashback_rules_menu_keyboard(),
        )
        return ConversationHandler.END

    percent = _parse_percent(text)
    if percent is None:
        await update.message.reply_text("❌ Введите число от 0 до 100.")
        return RULE_ADD_ENTER_PERCENT

    card_id = context.user_data.pop("cashback_rule_add_card_id", None)
    category_id = context.user_data.pop("cashback_rule_add_category_id", None)
    if not card_id or not category_id:
        await update.message.reply_text(
            "❌ Ошибка контекста. Повторите действие.",
            reply_markup=helpers.get_cashback_rules_menu_keyboard(),
        )
        return ConversationHandler.END

    month, year = _current_month_year()
    user_id = update.effective_user.id
    result = await cashback.create_user_cashback_rule(
        user_id=user_id,
        user_card_id=int(card_id),
        cashback_category_id=int(category_id),
        year=year,
        month=month,
        percent=percent,
    )
    if result["success"]:
        await update.message.reply_text(
            f"✅ Кэшбек добавлен на {month:02d}.{year}.",
            reply_markup=helpers.get_cashback_rules_menu_keyboard(),
        )
    else:
        await update.message.reply_text(
            f"❌ {result['message']}",
            reply_markup=helpers.get_cashback_rules_menu_keyboard(),
        )

    return ConversationHandler.END

async def cashback_rule_edit_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    month, year = _current_month_year()
    user_id = update.effective_user.id
    rules = await cashback.list_user_cashback_rules(user_id, year=year, month=month)
    if not rules:
        await update.message.reply_text(
            f"🧾 На {month:02d}.{year} правил пока нет.",
            reply_markup=helpers.get_cashback_rules_menu_keyboard(),
        )
        return ConversationHandler.END

    keyboard = []
    for rule in rules:
        emoji = cashback.get_cashback_category_emoji(rule["cashback_category_name"])
        text = f"💳 {rule['card_name']} | {emoji} {rule['cashback_category_name']} | {float(rule['percent']):.2f}%"
        keyboard.append([InlineKeyboardButton(text, callback_data=f"{CB_RULE_EDIT_PREFIX}{rule['id']}")])
    keyboard.append([InlineKeyboardButton("❌ Отмена", callback_data=f"{CB_RULE_EDIT_PREFIX}{CB_CANCEL}")])

    await update.message.reply_text(
        f"Выберите правило для редактирования ({month:02d}.{year}):",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return RULE_EDIT_SELECT


async def cashback_rule_edit_select(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    data = query.data[len(CB_RULE_EDIT_PREFIX):]
    if data == CB_CANCEL:
        await query.edit_message_text("❌ Изменение кэшбека отменено.")
        await query.message.reply_text("Выберите действие:", reply_markup=helpers.get_cashback_rules_menu_keyboard())
        return ConversationHandler.END

    context.user_data["cashback_rule_edit_id"] = int(data)
    await query.edit_message_text("Введите новый процент (0..100):")
    await query.message.reply_text("Ожидаю процент:", reply_markup=CANCEL_INPUT_KEYBOARD)
    return RULE_EDIT_ENTER_PERCENT


async def cashback_rule_edit_enter_percent(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = (update.message.text or "").strip()
    if text == "❌ Отмена":
        context.user_data.pop("cashback_rule_edit_id", None)
        await update.message.reply_text(
            "❌ Изменение кэшбека отменено.",
            reply_markup=helpers.get_cashback_rules_menu_keyboard(),
        )
        return ConversationHandler.END

    percent = _parse_percent(text)
    if percent is None:
        await update.message.reply_text("❌ Введите число от 0 до 100.")
        return RULE_EDIT_ENTER_PERCENT

    rule_id = context.user_data.pop("cashback_rule_edit_id", None)
    if not rule_id:
        await update.message.reply_text(
            "❌ Ошибка контекста. Повторите действие.",
            reply_markup=helpers.get_cashback_rules_menu_keyboard(),
        )
        return ConversationHandler.END

    user_id = update.effective_user.id
    result = await cashback.edit_user_cashback_rule(user_id, int(rule_id), percent)
    if result["success"]:
        await update.message.reply_text(
            "✅ Кэшбек обновлен.",
            reply_markup=helpers.get_cashback_rules_menu_keyboard(),
        )
    else:
        await update.message.reply_text(
            f"❌ {result['message']}",
            reply_markup=helpers.get_cashback_rules_menu_keyboard(),
        )

    return ConversationHandler.END


async def cashback_rule_delete_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    month, year = _current_month_year()
    user_id = update.effective_user.id
    rules = await cashback.list_user_cashback_rules(user_id, year=year, month=month)
    if not rules:
        await update.message.reply_text(
            f"🧾 На {month:02d}.{year} правил пока нет.",
            reply_markup=helpers.get_cashback_rules_menu_keyboard(),
        )
        return ConversationHandler.END

    keyboard = []
    for rule in rules:
        emoji = cashback.get_cashback_category_emoji(rule["cashback_category_name"])
        text = f"💳 {rule['card_name']} | {emoji} {rule['cashback_category_name']} | {float(rule['percent']):.2f}%"
        keyboard.append([InlineKeyboardButton(text, callback_data=f"{CB_RULE_DELETE_PREFIX}{rule['id']}")])
    keyboard.append([InlineKeyboardButton("❌ Отмена", callback_data=f"{CB_RULE_DELETE_PREFIX}{CB_CANCEL}")])

    await update.message.reply_text(
        f"Выберите правило для удаления ({month:02d}.{year}):",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return RULE_DELETE_SELECT


async def cashback_rule_delete_select(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    data = query.data[len(CB_RULE_DELETE_PREFIX):]
    if data == CB_CANCEL:
        await query.edit_message_text("❌ Удаление кэшбека отменено.")
        await query.message.reply_text("Выберите действие:", reply_markup=helpers.get_cashback_rules_menu_keyboard())
        return ConversationHandler.END

    user_id = update.effective_user.id
    result = await cashback.remove_user_cashback_rule(user_id, int(data))
    if result["success"]:
        await query.edit_message_text("✅ Кэшбек удален.")
    else:
        await query.edit_message_text(f"❌ {result['message']}")

    await query.message.reply_text("Выберите действие:", reply_markup=helpers.get_cashback_rules_menu_keyboard())
    return ConversationHandler.END


# Backward-compatible commands
async def cashback_rules_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    try:
        args = getattr(context, "args", None) or []
        month, year = _parse_month_year(args)
    except (ValueError, TypeError):
        await update.message.reply_text("❌ Неверный формат. Используйте: /cashback_rules [month] [year]")
        return

    if not (1 <= month <= 12):
        await update.message.reply_text("❌ Месяц должен быть от 1 до 12.")
        return

    rules = await cashback.list_user_cashback_rules(user_id, year=year, month=month)
    await update.message.reply_text(
        _format_rules(rules, month, year),
        reply_markup=helpers.get_cashback_rules_menu_keyboard(),
    )


async def cashback_card_add_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if not context.args:
        await update.message.reply_text("Использование: /cashback_card_add <название>")
        return

    name = " ".join(context.args).strip()
    result = await cashback.create_user_card(user_id, name)
    if result["success"]:
        await update.message.reply_text(f"✅ Карта добавлена: {result['card_name']}")
    else:
        await update.message.reply_text(f"❌ {result['message']}")


async def cashback_card_deactivate_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if len(context.args) != 1:
        await update.message.reply_text("Использование: /cashback_card_deactivate <card_id>")
        return
    try:
        card_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ card_id должен быть числом.")
        return

    result = await cashback.deactivate_user_card(user_id, card_id)
    if result["success"]:
        await update.message.reply_text(f"✅ Карта деактивирована: {result['card_name']}")
    else:
        await update.message.reply_text(f"❌ {result['message']}")


async def cashback_card_activate_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if len(context.args) != 1:
        await update.message.reply_text("Использование: /cashback_card_activate <card_id>")
        return
    try:
        card_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ card_id должен быть числом.")
        return

    result = await cashback.activate_user_card(user_id, card_id)
    if result["success"]:
        await update.message.reply_text(f"✅ Карта активирована: {result['card_name']}")
    else:
        await update.message.reply_text(f"❌ {result['message']}")


async def cashback_card_delete_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if len(context.args) != 1:
        await update.message.reply_text("Использование: /cashback_card_delete <card_id>")
        return
    try:
        card_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ card_id должен быть числом.")
        return

    result = await cashback.hard_delete_user_card(user_id, card_id)
    if result["success"]:
        await update.message.reply_text(f"✅ Карта удалена: {result['card_name']}")
    else:
        await update.message.reply_text(f"❌ {result['message']}")


async def cashback_category_add_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if not context.args:
        await update.message.reply_text("Использование: /cashback_category_add <название>")
        return

    name = " ".join(context.args).strip()
    result = await cashback.create_custom_cashback_category(user_id, name)
    if result["success"]:
        await update.message.reply_text(f"✅ Категория создана: {result['name']}")
    else:
        await update.message.reply_text(f"❌ {result['message']}")


async def cashback_rule_add_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if len(context.args) < 3:
        await update.message.reply_text(
            "Использование: /cashback_rule_add <card_id> <category_id> <percent> [month] [year]"
        )
        return

    try:
        card_id = int(context.args[0])
        category_id = int(context.args[1])
        percent = float(context.args[2].replace(",", "."))
        month, year = _current_month_year()
        if len(context.args) >= 4:
            month = int(context.args[3])
        if len(context.args) >= 5:
            year = int(context.args[4])
    except ValueError:
        await update.message.reply_text("❌ Проверьте формат чисел в команде.")
        return

    if not (1 <= month <= 12):
        await update.message.reply_text("❌ Месяц должен быть от 1 до 12.")
        return

    result = await cashback.create_user_cashback_rule(
        user_id=user_id,
        user_card_id=card_id,
        cashback_category_id=category_id,
        year=year,
        month=month,
        percent=percent,
    )
    if result["success"]:
        await update.message.reply_text(f"✅ Правило добавлено (ID {result['rule_id']}) на {month:02d}.{year}.")
    else:
        await update.message.reply_text(f"❌ {result['message']}")


async def cashback_rule_edit_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if len(context.args) != 2:
        await update.message.reply_text("Использование: /cashback_rule_edit <rule_id> <percent>")
        return

    try:
        rule_id = int(context.args[0])
        percent = float(context.args[1].replace(",", "."))
    except ValueError:
        await update.message.reply_text("❌ Проверьте формат чисел в команде.")
        return

    result = await cashback.edit_user_cashback_rule(user_id, rule_id, percent)
    if result["success"]:
        await update.message.reply_text(f"✅ Правило {result['rule_id']} обновлено.")
    else:
        await update.message.reply_text(f"❌ {result['message']}")


async def cashback_rule_remove_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if len(context.args) != 1:
        await update.message.reply_text("Использование: /cashback_rule_remove <rule_id>")
        return
    try:
        rule_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ rule_id должен быть числом.")
        return

    result = await cashback.remove_user_cashback_rule(user_id, rule_id)
    if result["success"]:
        await update.message.reply_text(f"✅ Правило {result['rule_id']} удалено.")
    else:
        await update.message.reply_text(f"❌ {result['message']}")


def register_cashback_handlers(application) -> None:
    application.add_handler(CommandHandler("cashback", cashback_menu))
    application.add_handler(CommandHandler("cashback_cards", cashback_cards_menu))
    application.add_handler(CommandHandler("cashback_rules", cashback_rules_command))
    application.add_handler(CommandHandler("cashback_stats", cashback_stats))
    application.add_handler(CommandHandler("cashback_card_add", cashback_card_add_command))
    application.add_handler(CommandHandler("cashback_card_deactivate", cashback_card_deactivate_command))
    application.add_handler(CommandHandler("cashback_card_activate", cashback_card_activate_command))
    application.add_handler(CommandHandler("cashback_card_delete", cashback_card_delete_command))
    application.add_handler(CommandHandler("cashback_category_add", cashback_category_add_command))
    application.add_handler(CommandHandler("cashback_rule_add", cashback_rule_add_command))
    application.add_handler(CommandHandler("cashback_rule_edit", cashback_rule_edit_command))
    application.add_handler(CommandHandler("cashback_rule_remove", cashback_rule_remove_command))

    application.add_handler(MessageHandler(filters.Regex(main_menu_button_regex("cashback")), cashback_menu))
    application.add_handler(MessageHandler(filters.Regex(cashback_menu_button_regex("cards")), cashback_cards_menu))
    application.add_handler(MessageHandler(filters.Regex(cashback_menu_button_regex("rules")), cashback_rules_menu))
    application.add_handler(MessageHandler(filters.Regex(cashback_menu_button_regex("categories")), cashback_categories_menu))
    application.add_handler(MessageHandler(filters.Regex(cashback_menu_button_regex("stats")), cashback_stats))
    application.add_handler(MessageHandler(filters.Regex(cashback_menu_button_regex("back")), cashback_back))

    application.add_handler(MessageHandler(filters.Regex(cashback_cards_menu_button_regex("list")), cashback_cards_list))
    application.add_handler(MessageHandler(filters.Regex(cashback_cards_menu_button_regex("back")), cashback_cards_back))
    application.add_handler(MessageHandler(filters.Regex(cashback_rules_menu_button_regex("back")), cashback_rules_back))
    application.add_handler(MessageHandler(filters.Regex(cashback_categories_menu_button_regex("list")), cashback_categories_list))
    application.add_handler(MessageHandler(filters.Regex(cashback_categories_menu_button_regex("back")), cashback_categories_back))

    application.add_handler(
        ConversationHandler(
            entry_points=[MessageHandler(filters.Regex(cashback_cards_menu_button_regex("add")), cashback_card_add_start)],
            states={CARD_ADD_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, cashback_card_add_input)]},
            fallbacks=[CommandHandler("cancel", cancel_to_cards_menu)],
            name="cashback_card_add_conversation",
            persistent=False,
        )
    )

    application.add_handler(
        ConversationHandler(
            entry_points=[MessageHandler(filters.Regex(cashback_cards_menu_button_regex("edit")), cashback_card_edit_start)],
            states={
                CARD_EDIT_SELECT: [CallbackQueryHandler(cashback_card_edit_select, pattern=rf"^{CB_CARD_EDIT_PREFIX}(\d+|{CB_CANCEL})$")],
                CARD_EDIT_ACTION_SELECT: [CallbackQueryHandler(cashback_card_edit_action, pattern=rf"^{CB_CARD_EDIT_ACTION_PREFIX}(activate|deactivate|{CB_CANCEL})$")],
            },
            fallbacks=[CommandHandler("cancel", cancel_to_cards_menu)],
            name="cashback_card_edit_conversation",
            persistent=False,
        )
    )

    application.add_handler(
        ConversationHandler(
            entry_points=[MessageHandler(filters.Regex(cashback_cards_menu_button_regex("delete")), cashback_card_delete_start)],
            states={
                CARD_DELETE_SELECT: [CallbackQueryHandler(cashback_card_delete_select, pattern=rf"^{CB_CARD_DELETE_PREFIX}(\d+|{CB_CANCEL})$")],
            },
            fallbacks=[CommandHandler("cancel", cancel_to_cards_menu)],
            name="cashback_card_delete_conversation",
            persistent=False,
        )
    )

    application.add_handler(
        ConversationHandler(
            entry_points=[MessageHandler(filters.Regex(cashback_categories_menu_button_regex("add")), cashback_category_add_start)],
            states={CATEGORY_ADD_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, cashback_category_add_input)]},
            fallbacks=[CommandHandler("cancel", cancel_to_categories_menu)],
            name="cashback_category_add_conversation",
            persistent=False,
        )
    )

    application.add_handler(
        ConversationHandler(
            entry_points=[MessageHandler(filters.Regex(cashback_categories_menu_button_regex("delete")), cashback_category_delete_start)],
            states={
                CATEGORY_DELETE_SELECT: [CallbackQueryHandler(cashback_category_delete_select, pattern=rf"^{CB_CAT_DELETE_PREFIX}(\d+|{CB_CANCEL})$")],
            },
            fallbacks=[CommandHandler("cancel", cancel_to_categories_menu)],
            name="cashback_category_delete_conversation",
            persistent=False,
        )
    )

    application.add_handler(
        ConversationHandler(
            entry_points=[MessageHandler(filters.Regex(cashback_rules_menu_button_regex("add")), cashback_rule_add_start)],
            states={
                RULE_ADD_SELECT_CARD: [CallbackQueryHandler(cashback_rule_add_select_card, pattern=rf"^{CB_RULE_ADD_CARD_PREFIX}(\d+|{CB_CANCEL})$")],
                RULE_ADD_SELECT_CATEGORY: [CallbackQueryHandler(cashback_rule_add_select_category, pattern=rf"^{CB_RULE_ADD_CAT_PREFIX}(\d+|{CB_CANCEL})$")],
                RULE_ADD_ENTER_PERCENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, cashback_rule_add_enter_percent)],
            },
            fallbacks=[CommandHandler("cancel", cancel_to_rules_menu)],
            name="cashback_rule_add_conversation",
            persistent=False,
        )
    )

    application.add_handler(
        ConversationHandler(
            entry_points=[MessageHandler(filters.Regex(cashback_rules_menu_button_regex("edit")), cashback_rule_edit_start)],
            states={
                RULE_EDIT_SELECT: [CallbackQueryHandler(cashback_rule_edit_select, pattern=rf"^{CB_RULE_EDIT_PREFIX}(\d+|{CB_CANCEL})$")],
                RULE_EDIT_ENTER_PERCENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, cashback_rule_edit_enter_percent)],
            },
            fallbacks=[CommandHandler("cancel", cancel_to_rules_menu)],
            name="cashback_rule_edit_conversation",
            persistent=False,
        )
    )

    application.add_handler(
        ConversationHandler(
            entry_points=[MessageHandler(filters.Regex(cashback_rules_menu_button_regex("delete")), cashback_rule_delete_start)],
            states={
                RULE_DELETE_SELECT: [CallbackQueryHandler(cashback_rule_delete_select, pattern=rf"^{CB_RULE_DELETE_PREFIX}(\d+|{CB_CANCEL})$")],
            },
            fallbacks=[CommandHandler("cancel", cancel_to_rules_menu)],
            name="cashback_rule_delete_conversation",
            persistent=False,
        )
    )
