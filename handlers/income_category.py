"""Обработчики управления категориями доходов."""

from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler, CommandHandler, MessageHandler, CallbackQueryHandler, filters

import config
from utils import helpers, income_categories, projects
from utils.helpers import income_menu_button_regex
from utils.logger import get_logger

logger = get_logger("handlers.income_category")

ENTERING_NAME, CHOOSING_CATEGORY = range(2)


def _category_menu_keyboard() -> ReplyKeyboardMarkup:
    keyboard = [
        ["➕ Добавить категорию", "📋 Список категорий"],
        ["🗑️ Удалить категорию", config.INCOME_MENU_BUTTONS["back"]],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


async def income_categories_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Открывает меню категорий доходов."""
    await update.message.reply_text(
        "📂 Категории доходов\n\nВыберите действие:",
        reply_markup=_category_menu_keyboard(),
    )


async def add_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Старт создания категории дохода."""
    await update.message.reply_text("Введите название новой категории дохода:")
    return ENTERING_NAME


async def add_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Создает категорию дохода по введенному имени."""
    user_id = update.effective_user.id
    project_id = context.user_data.get("active_project_id")
    category_name = update.message.text.strip()

    result = await income_categories.create_income_category(
        user_id=user_id,
        name=category_name,
        project_id=project_id,
        is_system=False,
    )

    if not result["success"]:
        await update.message.reply_text(f"❌ {result['message']}")
        return ENTERING_NAME

    emoji = config.DEFAULT_INCOME_CATEGORIES.get(result["name"], "💵")
    await update.message.reply_text(
        f"✅ {result['message']}\n{emoji} {result['name']}",
        reply_markup=_category_menu_keyboard(),
    )
    return ConversationHandler.END


async def list_categories(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывает список категорий доходов."""
    user_id = update.effective_user.id
    project_id = context.user_data.get("active_project_id")

    await income_categories.ensure_system_income_categories_exist(user_id)
    categories_list = await income_categories.get_income_categories_for_user_project(user_id, project_id)

    if not categories_list:
        await update.message.reply_text("❌ Нет доступных категорий доходов.", reply_markup=_category_menu_keyboard())
        return

    project_context = "📊 Общие доходы"
    if project_id is not None:
        project = await projects.get_project_by_id(user_id, project_id)
        if project:
            project_context = f"📁 Проект: {project['project_name']}"

    system = [cat for cat in categories_list if cat["is_system"]]
    custom = [cat for cat in categories_list if not cat["is_system"]]

    message = f"📋 Список категорий доходов\n\n{project_context}\n\n"
    if system:
        message += "🔵 Системные:\n"
        for cat in system:
            emoji = config.DEFAULT_INCOME_CATEGORIES.get(cat["name"], "💵")
            message += f"{emoji} {cat['name']}\n"
        message += "\n"

    if custom:
        message += "🟢 Пользовательские:\n"
        for cat in custom:
            emoji = config.DEFAULT_INCOME_CATEGORIES.get(cat["name"], "💵")
            message += f"{emoji} {cat['name']}\n"

    await update.message.reply_text(message, reply_markup=_category_menu_keyboard())


async def deactivate_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Показывает список пользовательских категорий доходов для деактивации."""
    user_id = update.effective_user.id
    project_id = context.user_data.get("active_project_id")

    categories_list = await income_categories.get_income_categories_for_user_project(user_id, project_id)
    custom = [cat for cat in categories_list if not cat["is_system"]]

    if not custom:
        await update.message.reply_text("❌ Нет пользовательских категорий для деактивации.", reply_markup=_category_menu_keyboard())
        return ConversationHandler.END

    keyboard = []
    row = []
    for idx, cat in enumerate(custom):
        emoji = config.DEFAULT_INCOME_CATEGORIES.get(cat["name"], "💵")
        row.append(InlineKeyboardButton(f"{emoji} {cat['name']}", callback_data=f"inc_del_{cat['income_category_id']}"))
        if (idx + 1) % 2 == 0 or idx == len(custom) - 1:
            keyboard.append(row)
            row = []

    keyboard.append([InlineKeyboardButton("❌ Отмена", callback_data="inc_del_cancel")])
    await update.message.reply_text(
        "Выберите категорию дохода для деактивации:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return CHOOSING_CATEGORY


async def deactivate_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Деактивирует выбранную категорию дохода."""
    query = update.callback_query
    await query.answer()

    if query.data == "inc_del_cancel":
        await query.edit_message_text("Операция отменена.")
        return ConversationHandler.END

    try:
        income_category_id = int(query.data.split("_")[2])
    except (ValueError, IndexError):
        await query.edit_message_text("❌ Ошибка выбора категории.")
        return ConversationHandler.END

    result = await income_categories.deactivate_income_category(update.effective_user.id, income_category_id)
    if result["success"]:
        await query.edit_message_text(f"✅ {result['message']}")
    else:
        await query.edit_message_text(f"❌ {result['message']}\n\nПодсказка: откройте '🔁 Постоянный доход' и измените/удалите активные правила.")

    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Отмена диалога категории дохода."""
    return await helpers.cancel_conversation(update, context, "Операция отменена.", restore_keyboard=True)


def register_income_category_handlers(application):
    """Регистрирует хендлеры категорий доходов."""
    application.add_handler(MessageHandler(filters.Regex(income_menu_button_regex("categories")), income_categories_menu))

    add_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex(r"^➕ Добавить категорию$"), add_start)],
        states={
            ENTERING_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_name)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        name="income_category_add_conversation",
        persistent=False,
    )
    application.add_handler(add_conv)

    application.add_handler(MessageHandler(filters.Regex(r"^📋 Список категорий$"), list_categories))

    deactivate_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex(r"^🗑️ Удалить категорию$"), deactivate_start)],
        states={
            CHOOSING_CATEGORY: [CallbackQueryHandler(deactivate_callback, pattern=r"^inc_del_")],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        name="income_category_deactivate_conversation",
        persistent=False,
    )
    application.add_handler(deactivate_conv)
