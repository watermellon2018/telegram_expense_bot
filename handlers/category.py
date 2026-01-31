"""
Обработчики команд для управления категориями
"""

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler, ConversationHandler, MessageHandler, filters
from utils import categories, helpers, projects
from utils.helpers import main_menu_button_regex, category_menu_button_regex
from utils.logger import get_logger, log_event, log_error
import config

logger = get_logger("handlers.category")

# Состояния для ConversationHandler
CHOOSING_CATEGORY_TO_DELETE, CONFIRMING_DELETE, CONFIRMING_DELETE_WITH_EXPENSES, ENTERING_CATEGORY_NAME = range(4)


async def delete_category_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Обрабатывает команду /delete_category для начала процесса удаления категории
    """
    user_id = update.effective_user.id
    project_id = context.user_data.get('active_project_id')
    
    log_event(logger, "delete_category_start", user_id=user_id, project_id=project_id)
    
    # Получаем все категории пользователя (включая неактивные для отображения)
    await categories.ensure_system_categories_exist(user_id)
    
    # Получаем только активные категории для выбора
    cats = await categories.get_categories_for_user_project(user_id, project_id)
    
    if not cats:
        await update.message.reply_text(
            "❌ Нет доступных категорий для удаления."
        )
        return ConversationHandler.END
    
    # Фильтруем: показываем только пользовательские категории (не системные)
    user_categories = [cat for cat in cats if not cat['is_system']]
    
    if not user_categories:
        await update.message.reply_text(
            "ℹ️ Системные категории нельзя удалить.\n"
            "Вы можете удалять только созданные вами категории."
        )
        return ConversationHandler.END
    
    # Создаем inline клавиатуру с категориями для удаления
    keyboard = []
    row = []
    
    for i, cat in enumerate(user_categories):
        emoji = config.DEFAULT_CATEGORIES.get(cat['name'], '📦')
        button_text = f"{emoji} {cat['name']}"
        
        row.append(InlineKeyboardButton(
            button_text,
            callback_data=f"delcat_{cat['category_id']}"
        ))
        
        # По 2 кнопки в ряд
        if (i + 1) % 2 == 0 or i == len(user_categories) - 1:
            keyboard.append(row)
            row = []
    
    keyboard.append([InlineKeyboardButton("❌ Отмена", callback_data="delcat_cancel")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "🗑️ Выберите категорию для удаления:\n\n"
        "ℹ️ Если категория используется в расходах, они будут перенесены в категорию 'Прочее'.",
        reply_markup=reply_markup
    )
    
    return CHOOSING_CATEGORY_TO_DELETE


async def handle_category_delete_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Обрабатывает выбор категории для удаления через callback
    """
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    callback_data = query.data
    
    if callback_data == "delcat_cancel":
        await query.edit_message_text("❌ Удаление категории отменено.")
        return ConversationHandler.END
    
    # Извлекаем category_id из callback_data
    if not callback_data.startswith("delcat_"):
        await query.edit_message_text("❌ Ошибка выбора категории.")
        return ConversationHandler.END
    
    try:
        category_id = int(callback_data.split("_")[1])
    except (ValueError, IndexError):
        await query.edit_message_text("❌ Ошибка выбора категории.")
        return ConversationHandler.END
    
    # Получаем информацию о категории
    category = await categories.get_category_by_id(user_id, category_id)
    if not category:
        await query.edit_message_text("❌ Категория не найдена.")
        return ConversationHandler.END
    
    # Проверяем, что это не системная категория
    if category['is_system']:
        await query.edit_message_text(
            "❌ Системные категории нельзя удалить."
        )
        return ConversationHandler.END
    
    # Сохраняем category_id в контексте
    context.user_data['delete_category_id'] = category_id
    context.user_data['delete_category_name'] = category['name']
    
    # Проверяем использование категории
    from utils import db
    usage_count = await db.fetchval(
        """
        SELECT COUNT(*) FROM expenses
        WHERE category_id = $1 AND user_id = $2
        """,
        category_id,
        str(user_id)
    )
    
    # Сохраняем количество использований в контексте
    context.user_data['delete_category_usage_count'] = usage_count or 0
    
    emoji = config.DEFAULT_CATEGORIES.get(category['name'], '📦')
    
    if usage_count > 0:
        # Если есть расходы, показываем специальное подтверждение с предупреждением о переносе
        keyboard = [
            [
                InlineKeyboardButton("✅ Да, удалить и перенести", callback_data="delcat_confirm_with_transfer"),
                InlineKeyboardButton("❌ Отмена", callback_data="delcat_cancel")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"⚠️ Категория {emoji} {category['name']} используется в {usage_count} расходах.\n\n"
            f"При удалении все расходы будут автоматически перенесены в категорию '📦 Прочее'.\n\n"
            f"Вы уверены, что хотите удалить категорию?",
            reply_markup=reply_markup
        )
        
        return CONFIRMING_DELETE_WITH_EXPENSES
    else:
        # Если расходов нет, обычное подтверждение
        keyboard = [
            [
                InlineKeyboardButton("✅ Да, удалить", callback_data="delcat_confirm"),
                InlineKeyboardButton("❌ Отмена", callback_data="delcat_cancel")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"⚠️ Вы уверены, что хотите удалить категорию?\n\n"
            f"{emoji} {category['name']}\n\n"
            f"Это действие нельзя отменить.",
            reply_markup=reply_markup
        )
        
        return CONFIRMING_DELETE


async def confirm_category_delete(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Подтверждает удаление категории (без расходов)
    """
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    callback_data = query.data
    
    if callback_data == "delcat_cancel":
        await query.edit_message_text("❌ Удаление категории отменено.")
        # Очищаем контекст
        context.user_data.pop('delete_category_id', None)
        context.user_data.pop('delete_category_name', None)
        context.user_data.pop('delete_category_usage_count', None)
        return ConversationHandler.END
    
    if callback_data != "delcat_confirm":
        await query.edit_message_text("❌ Неверная команда.")
        return ConversationHandler.END
    
    category_id = context.user_data.get('delete_category_id')
    category_name = context.user_data.get('delete_category_name')
    
    if not category_id:
        await query.edit_message_text("❌ Ошибка: категория не выбрана.")
        return ConversationHandler.END
    
    # Выполняем удаление (деактивацию)
    result = await categories.deactivate_category(user_id, category_id)
    
    # Очищаем контекст
    context.user_data.pop('delete_category_id', None)
    context.user_data.pop('delete_category_name', None)
    context.user_data.pop('delete_category_usage_count', None)
    
    if result['success']:
        emoji = config.DEFAULT_CATEGORIES.get(category_name, '📦')
        log_event(logger, "category_deleted", user_id=user_id, 
                 category_id=category_id, category_name=category_name)
        
        # Возвращаемся в меню категорий
        btn = config.CATEGORY_MENU_BUTTONS
        keyboard = [
            [btn["add"], btn["list"]],
            [btn["delete"], btn["back"]],
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        
        await query.edit_message_text(f"✅ Категория {emoji} {category_name} успешно удалена.")
        await query.message.reply_text(
            "📂 Управление категориями\n\nВыберите действие:",
            reply_markup=reply_markup
        )
    else:
        log_error(logger, Exception(result.get('message', 'Unknown error')), 
                 "category_delete_failed", user_id=user_id, category_id=category_id)
        await query.edit_message_text(
            f"❌ {result['message']}"
        )
    
    return ConversationHandler.END


async def confirm_category_delete_with_transfer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Подтверждает удаление категории с переносом расходов в 'Прочее'
    """
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    callback_data = query.data
    
    if callback_data == "delcat_cancel":
        await query.edit_message_text("❌ Удаление категории отменено.")
        # Очищаем контекст
        context.user_data.pop('delete_category_id', None)
        context.user_data.pop('delete_category_name', None)
        context.user_data.pop('delete_category_usage_count', None)
        return ConversationHandler.END
    
    if callback_data != "delcat_confirm_with_transfer":
        await query.edit_message_text("❌ Неверная команда.")
        return ConversationHandler.END
    
    category_id = context.user_data.get('delete_category_id')
    category_name = context.user_data.get('delete_category_name')
    usage_count = context.user_data.get('delete_category_usage_count', 0)
    
    if not category_id:
        await query.edit_message_text("❌ Ошибка: категория не выбрана.")
        return ConversationHandler.END
    
    # Убеждаемся, что категория 'Прочее' существует
    await categories.ensure_system_categories_exist(user_id)
    
    # Находим категорию 'Прочее'
    project_id = context.user_data.get('active_project_id')
    all_cats = await categories.get_categories_for_user_project(user_id, project_id)
    prochee_category = None
    
    # Ищем в категориях проекта
    for cat in all_cats:
        if cat['name'].lower() == 'прочее':
            prochee_category = cat
            break
    
    # Если не найдено в проекте, ищем в глобальных
    if not prochee_category:
        global_cats = await categories.get_categories_for_user_project(user_id, None)
        for cat in global_cats:
            if cat['name'].lower() == 'прочее':
                prochee_category = cat
                break
    
    if not prochee_category:
        log_error(logger, Exception("Прочее category not found"), 
                 "delete_category_prochee_not_found", user_id=user_id)
        await query.edit_message_text(
            "❌ Ошибка: категория 'Прочее' не найдена. Попробуйте позже."
        )
        return ConversationHandler.END
    
    # Выполняем удаление с переносом расходов
    result = await categories.delete_category_with_transfer(
        user_id, 
        category_id, 
        prochee_category['category_id']
    )
    
    # Очищаем контекст
    context.user_data.pop('delete_category_id', None)
    context.user_data.pop('delete_category_name', None)
    context.user_data.pop('delete_category_usage_count', None)
    
    if result['success']:
        emoji = config.DEFAULT_CATEGORIES.get(category_name, '📦')
        log_event(logger, "category_deleted_with_transfer", user_id=user_id,
                 category_id=category_id, category_name=category_name,
                 transferred_count=result.get('transferred_count', 0))
        
        # Возвращаемся в меню категорий
        btn = config.CATEGORY_MENU_BUTTONS
        keyboard = [
            [btn["add"], btn["list"]],
            [btn["delete"], btn["back"]],
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        
        await query.edit_message_text(
            f"✅ Категория {emoji} {category_name} удалена.\n\n"
            f"📦 {result.get('transferred_count', usage_count)} расходов перенесено в 'Прочее'."
        )
        await query.message.reply_text(
            "📂 Управление категориями\n\nВыберите действие:",
            reply_markup=reply_markup
        )
    else:
        log_error(logger, Exception(result.get('message', 'Unknown error')), 
                 "category_delete_with_transfer_failed", user_id=user_id, category_id=category_id)
        await query.edit_message_text(
            f"❌ {result['message']}"
        )
    
    return ConversationHandler.END


async def cancel_category_delete(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Отменяет процесс удаления категории
    """
    # Очищаем контекст
    context.user_data.pop('delete_category_id', None)
    context.user_data.pop('delete_category_name', None)
    context.user_data.pop('delete_category_usage_count', None)
    
    return await helpers.cancel_conversation(update, context, "Удаление категории отменено.")


async def categories_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Показывает меню управления категориями
    """
    user_id = update.effective_user.id
    project_id = context.user_data.get('active_project_id')
    
    log_event(logger, "categories_menu_opened", user_id=user_id, project_id=project_id)
    
    # Получаем информацию о проекте для отображения контекста
    project_context = "📊 Общие расходы"
    if project_id is not None:
        project = await projects.get_project_by_id(user_id, project_id)
        if project:
            project_context = f"📁 Проект: {project['project_name']}"
    
    # Создаем клавиатуру меню категорий
    btn = config.CATEGORY_MENU_BUTTONS
    keyboard = [
        [btn["add"], btn["list"]],
        [btn["delete"], btn["back"]],
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
    await update.message.reply_text(
        f"📂 Управление категориями\n\n"
        f"{project_context}\n\n"
        f"Выберите действие:",
        reply_markup=reply_markup
    )


async def category_add_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Обрабатывает нажатие кнопки "➕ Добавить категорию"
    """
    user_id = update.effective_user.id
    project_id = context.user_data.get('active_project_id')
    
    log_event(logger, "category_add_start", user_id=user_id, project_id=project_id)
    
    project_context = "📊 Общие расходы"
    if project_id is not None:
        project = await projects.get_project_by_id(user_id, project_id)
        if project:
            project_context = f"📁 Проект: {project['project_name']}"
    
    await update.message.reply_text(
        f"{project_context}\n\n"
        f"Введите название новой категории:",
        reply_markup=ReplyKeyboardMarkup([["❌ Отмена"]], resize_keyboard=True)
    )
    
    return ENTERING_CATEGORY_NAME


async def handle_category_name_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Обрабатывает ввод названия категории
    """
    user_id = update.effective_user.id
    project_id = context.user_data.get('active_project_id')
    category_name = update.message.text.strip()
    
    if category_name == "❌ Отмена":
        return await cancel_category_add(update, context)
    
    if not category_name:
        await update.message.reply_text(
            "❌ Название категории не может быть пустым. Введите название:"
        )
        return ENTERING_CATEGORY_NAME
    
    # Создаем категорию
    result = await categories.create_category(
        user_id=user_id,
        name=category_name,
        project_id=project_id,
        is_system=False
    )
    
    if result['success']:
        emoji = config.DEFAULT_CATEGORIES.get(category_name, '📦')
        log_event(logger, "category_added_from_menu", user_id=user_id,
                 category_id=result['category_id'], category_name=category_name, project_id=project_id)
        
        project_context = "📊 Общие расходы"
        if project_id is not None:
            project = await projects.get_project_by_id(user_id, project_id)
            if project:
                project_context = f"📁 Проект: {project['project_name']}"
        
        # Возвращаемся в меню категорий
        btn = config.CATEGORY_MENU_BUTTONS
        keyboard = [
            [btn["add"], btn["list"]],
            [btn["delete"], btn["back"]],
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        
        await update.message.reply_text(
            f"✅ {result['message']}\n\n"
            f"{emoji} {category_name}\n\n"
            f"{project_context}",
            reply_markup=reply_markup
        )
    else:
        await update.message.reply_text(
            f"❌ {result['message']}\n\nПопробуйте другое название:"
        )
        return ENTERING_CATEGORY_NAME
    
    return ConversationHandler.END


async def category_list_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Обрабатывает нажатие кнопки "📋 Список категорий"
    """
    user_id = update.effective_user.id
    project_id = context.user_data.get('active_project_id')
    
    log_event(logger, "category_list_viewed", user_id=user_id, project_id=project_id)
    
    # Убеждаемся, что системные категории существуют
    await categories.ensure_system_categories_exist(user_id)
    
    # Получаем категории
    cats = await categories.get_categories_for_user_project(user_id, project_id)
    
    if not cats:
        await update.message.reply_text(
            "❌ Нет доступных категорий."
        )
        return
    
    # Формируем список категорий
    project_context = "📊 Общие расходы"
    if project_id is not None:
        project = await projects.get_project_by_id(user_id, project_id)
        if project:
            project_context = f"📁 Проект: {project['project_name']}"
    
    message = f"📋 Список категорий\n\n{project_context}\n\n"
    
    # Разделяем системные и пользовательские
    system_cats = [cat for cat in cats if cat['is_system']]
    user_cats = [cat for cat in cats if not cat['is_system']]
    
    if system_cats:
        message += "🔵 Системные категории:\n"
        for cat in system_cats:
            emoji = config.DEFAULT_CATEGORIES.get(cat['name'], '📦')
            message += f"{emoji} {cat['name']}\n"
        message += "\n"
    
    if user_cats:
        message += "🟢 Ваши категории:\n"
        for cat in user_cats:
            emoji = config.DEFAULT_CATEGORIES.get(cat['name'], '📦')
            message += f"{emoji} {cat['name']}\n"
    
    # Возвращаемся в меню категорий
    btn = config.CATEGORY_MENU_BUTTONS
    keyboard = [
        [btn["add"], btn["list"]],
        [btn["delete"], btn["back"]],
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
    await update.message.reply_text(message, reply_markup=reply_markup)


async def category_delete_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Обрабатывает нажатие кнопки "🗑️ Удалить категорию"
    """
    return await delete_category_command(update, context)


async def category_back_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Обрабатывает нажатие кнопки "⬅️ Назад" - возврат в главное меню
    """
    user_id = update.effective_user.id
    log_event(logger, "categories_menu_closed", user_id=user_id)
    
    await update.message.reply_text(
        "⬅️ Возврат в главное меню",
        reply_markup=helpers.get_main_menu_keyboard()
    )


async def cancel_category_add(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Отменяет создание категории
    """
    btn = config.CATEGORY_MENU_BUTTONS
    keyboard = [
        [btn["add"], btn["list"]],
        [btn["delete"], btn["back"]],
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
    await update.message.reply_text(
        "❌ Создание категории отменено.",
        reply_markup=reply_markup
    )
    
    return ConversationHandler.END


def register_category_handlers(application):
    """
    Регистрирует обработчики команд для управления категориями
    """
    # Меню категорий (кнопка из главного меню)
    application.add_handler(MessageHandler(
        filters.Regex(main_menu_button_regex("categories")), 
        categories_menu
    ))
    
    # Кнопки меню категорий (list и back - простые, add и delete в ConversationHandler)
    application.add_handler(MessageHandler(
        filters.Regex(category_menu_button_regex("list")),
        category_list_button
    ))
    application.add_handler(MessageHandler(
        filters.Regex(category_menu_button_regex("back")),
        category_back_button
    ))
    
    # Conversation для создания категории
    create_conv_handler = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex(category_menu_button_regex("add")), category_add_button),
        ],
        states={
            ENTERING_CATEGORY_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_category_name_input)
            ],
        },
        fallbacks=[
            MessageHandler(filters.Regex("^❌ Отмена$"), cancel_category_add),
            CommandHandler("cancel", cancel_category_add)
        ],
        name="create_category_conversation",
        persistent=False
    )
    application.add_handler(create_conv_handler)
    
    # Conversation для удаления категории
    delete_conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("delete_category", delete_category_command),
            MessageHandler(filters.Regex(category_menu_button_regex("delete")), category_delete_button),
        ],
        states={
            CHOOSING_CATEGORY_TO_DELETE: [
                CallbackQueryHandler(handle_category_delete_callback, pattern=r'^delcat_')
            ],
            CONFIRMING_DELETE: [
                CallbackQueryHandler(confirm_category_delete, pattern=r'^delcat_(confirm|cancel)$')
            ],
            CONFIRMING_DELETE_WITH_EXPENSES: [
                CallbackQueryHandler(confirm_category_delete_with_transfer, pattern=r'^delcat_(confirm_with_transfer|cancel)$')
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel_category_delete)],
        name="delete_category_conversation",
        persistent=False
    )
    application.add_handler(delete_conv_handler)
