"""Обработчики для добавления доходов."""

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler, ConversationHandler, MessageHandler, CallbackQueryHandler, filters

import config
from utils import helpers, projects
from utils import income_categories
from utils import incomes
from utils.helpers import income_menu_button_regex
from utils.logger import get_logger, log_event

logger = get_logger("handlers.income")

ENTERING_AMOUNT, CHOOSING_CATEGORY, ENTERING_DESCRIPTION, CREATING_CATEGORY = range(4)


async def income_add_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Старт диалога добавления дохода."""
    user_id = update.effective_user.id
    project_id = await helpers.get_active_project_id(user_id, context)

    from utils.permissions import Permission, has_permission
    if not await has_permission(user_id, project_id, Permission.ADD_EXPENSE):
        await update.message.reply_text("❌ У вас нет прав на добавление доходов в этом проекте.")
        return ConversationHandler.END

    await update.message.reply_text("Введите сумму дохода:")
    return ENTERING_AMOUNT


async def handle_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обрабатывает сумму дохода и показывает категории."""
    user_id = update.effective_user.id
    project_id = context.user_data.get("active_project_id")

    try:
        amount = float(update.message.text.replace(",", "."))
        if amount <= 0:
            await update.message.reply_text("❌ Сумма должна быть больше нуля. Введите сумму:")
            return ENTERING_AMOUNT
    except ValueError:
        await update.message.reply_text("❌ Неверный формат суммы. Например: 1000")
        return ENTERING_AMOUNT

    context.user_data["income_amount"] = amount

    await income_categories.ensure_system_income_categories_exist(user_id)
    cats = await income_categories.get_income_categories_for_user_project(user_id, project_id)
    if not cats:
        await update.message.reply_text("❌ Нет доступных категорий доходов.")
        return ConversationHandler.END

    keyboard = []
    row = []
    for idx, cat in enumerate(cats):
        emoji = config.DEFAULT_INCOME_CATEGORIES.get(cat["name"], "💵")
        row.append(InlineKeyboardButton(f"{emoji} {cat['name']}", callback_data=f"icat_{cat['income_category_id']}"))
        if (idx + 1) % 2 == 0 or idx == len(cats) - 1:
            keyboard.append(row)
            row = []

    keyboard.append([InlineKeyboardButton("➕ Создать категорию", callback_data="icat_create")])
    await update.message.reply_text(
        f"Сумма: {amount:.2f}\n\nВыберите категорию дохода:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return CHOOSING_CATEGORY


async def handle_category_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обрабатывает выбор категории дохода через callback."""
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id
    project_id = context.user_data.get("active_project_id")

    if query.data == "icat_create":
        await query.edit_message_text("Введите название новой категории дохода:")
        return CREATING_CATEGORY

    if not query.data.startswith("icat_"):
        await query.edit_message_text("❌ Ошибка выбора категории.")
        return ConversationHandler.END

    try:
        income_category_id = int(query.data.split("_")[1])
    except (ValueError, IndexError):
        await query.edit_message_text("❌ Ошибка выбора категории.")
        return ConversationHandler.END

    category = await income_categories.get_income_category_by_id(user_id, income_category_id)
    if not category and project_id is not None:
        category = await income_categories.get_income_category_by_id_only(income_category_id)
    if not category:
        await query.edit_message_text("❌ Категория дохода не найдена.")
        return ConversationHandler.END

    context.user_data["income_category_id"] = income_category_id
    context.user_data["income_category_name"] = category["name"]

    await query.edit_message_text(
        f"Сумма: {context.user_data.get('income_amount', 0):.2f}\n"
        f"Категория: {category['name']}\n\n"
        "Введите описание дохода или /skip, чтобы пропустить:"
    )
    return ENTERING_DESCRIPTION


async def handle_create_category(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Создание новой категории дохода в процессе добавления дохода."""
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
        await update.message.reply_text(f"❌ {result['message']}\n\nВведите другое название:")
        return CREATING_CATEGORY

    context.user_data["income_category_id"] = result["income_category_id"]
    context.user_data["income_category_name"] = result["name"]
    await update.message.reply_text(
        f"✅ Категория '{result['name']}' создана.\n"
        "Введите описание дохода или /skip, чтобы пропустить:"
    )
    return ENTERING_DESCRIPTION


async def handle_description(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Финальный шаг добавления дохода."""
    user_id = update.effective_user.id
    amount = context.user_data.get("income_amount")
    income_category_id = context.user_data.get("income_category_id")
    income_category_name = context.user_data.get("income_category_name", "")
    project_id = context.user_data.get("active_project_id")

    if not amount or not income_category_id:
        await update.message.reply_text("❌ Ошибка: не удалось определить сумму или категорию.")
        return ConversationHandler.END

    description = "" if update.message.text == "/skip" else update.message.text

    success = await incomes.add_income(
        user_id=user_id,
        amount=amount,
        income_category_id=income_category_id,
        description=description,
        project_id=project_id,
    )

    for key in ["income_amount", "income_category_id", "income_category_name"]:
        context.user_data.pop(key, None)

    if not success:
        await update.message.reply_text("❌ Ошибка при добавлении дохода.", reply_markup=helpers.get_main_menu_keyboard())
        return ConversationHandler.END

    project_line = "📊 Общие доходы"
    if project_id is not None:
        project = await projects.get_project_by_id(user_id, project_id)
        if project:
            project_line = f"📁 Проект: {project['project_name']}"

    emoji = config.DEFAULT_INCOME_CATEGORIES.get(income_category_name, "💵")
    message = (
        "✅ Доход добавлен:\n"
        f"💰 Сумма: {amount:.2f}\n"
        f"{emoji} Категория: {income_category_name}\n"
        f"{project_line}"
    )
    if description:
        message += f"\n📝 Описание: {description}"

    log_event(logger, "income_added", user_id=user_id, project_id=project_id, amount=amount)
    await update.message.reply_text(message, reply_markup=helpers.get_main_menu_keyboard())
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Отмена диалога добавления дохода."""
    for key in ["income_amount", "income_category_id", "income_category_name"]:
        context.user_data.pop(key, None)
    return await helpers.cancel_conversation(update, context, "Добавление дохода отменено.")


def register_income_handlers(application):
    """Регистрирует обработчики добавления доходов."""
    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("income_add", income_add_start),
            MessageHandler(filters.Regex(income_menu_button_regex("add")), income_add_start),
        ],
        states={
            ENTERING_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_amount)],
            CHOOSING_CATEGORY: [CallbackQueryHandler(handle_category_callback, pattern=r"^icat_")],
            CREATING_CATEGORY: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_create_category)],
            ENTERING_DESCRIPTION: [
                CommandHandler("skip", handle_description),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_description),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        name="add_income_conversation",
        persistent=False,
    )
    application.add_handler(conv_handler)
