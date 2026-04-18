"""
Обработчики команд для добавления расходов
"""

import asyncio

from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler, filters, MessageHandler, ConversationHandler, CallbackQueryHandler
from utils import excel, helpers, projects, categories
from utils.helpers import main_menu_button_regex
from utils.budget_notifier import check_user_budget_now
from utils.logger import get_logger, log_command, log_event, log_error
import config
from metrics import (
    track_command,
    track_handler_start,
    track_handler_success,
    track_handler_error,
    track_flow_started,
    track_flow_completed,
    track_flow_cancelled,
    classify_error_type,
)

logger = get_logger("handlers.expense")

# Состояния для ConversationHandler
ENTERING_AMOUNT, CHOOSING_CATEGORY, ENTERING_DESCRIPTION, CREATING_CATEGORY = range(4)


async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Обрабатывает текстовые сообщения, пытаясь распознать добавление расхода
    """
    import time
    start_time = time.time()
    
    user_id = update.effective_user.id
    message_text = update.message.text
    request_id = context.user_data.get('request_id')

    log_event(logger, "text_message_processing", request_id=request_id, 
             user_id=user_id, text_preview=message_text[:100], text_length=len(message_text))

    # Пытаемся распарсить как команду добавления расхода
    expense_data = helpers.parse_add_command(message_text)

    if expense_data:
        # Получаем активный проект (загружает из БД если нужно)
        project_id = await helpers.get_active_project_id(user_id, context)

        # Проверяем право добавления расхода
        from utils.permissions import Permission, has_permission
        if not await has_permission(user_id, project_id, Permission.ADD_EXPENSE):
            await update.message.reply_text(
                "❌ У вас нет прав на добавление расходов в этом проекте."
            )
            return

        # Ищем категорию по имени одним SQL-запросом
        category_found = await categories.get_category_by_name(
            user_id, expense_data['category'], project_id
        )

        if not category_found:
            log_event(logger, "invalid_category_in_text", user_id=user_id,
                     category=expense_data['category'],
                     message="Category not found in text message")
            return  # Не отвечаем, если категория не найдена в обычном сообщении
        
        log_event(logger, "expense_parsed_from_text", user_id=user_id, 
                 amount=expense_data['amount'], category_id=category_found['category_id'],
                 category_name=category_found['name'],
                 has_description=bool(expense_data['description']), project_id=project_id)
        
        # Добавляем расход
        success = await excel.add_expense(
            user_id,
            expense_data['amount'],
            category_found['category_id'],
            expense_data['description'],
            project_id
        )

        if not success:
            duration_ms = (time.time() - start_time) * 1000
            log_error(logger, Exception("Failed to add expense from text"), 
                     "expense_add_failed_from_text", request_id=request_id,
                     duration_ms=duration_ms, user_id=user_id,
                     amount=expense_data['amount'], category_id=category_found['category_id'],
                     category_name=category_found['name'])
            await update.message.reply_text("❌ Ошибка при добавлении расхода. Попробуйте еще раз.")
            return

        # Отправляем подтверждение
        category_emoji = config.DEFAULT_CATEGORIES.get(category_found['name'], '📦')

        confirmation = (
            f"✅ Расход добавлен:\n"
            f"💰 Сумма: {expense_data['amount']}\n"
            f"{category_emoji} Категория: {category_found['name'].title()}"
        )

        if expense_data['description']:
            confirmation += f"\n📝 Описание: {expense_data['description'].title()}"
        
        # Добавляем информацию о проекте
        if project_id is not None:
            try:
                project = await projects.get_project_by_id(user_id, project_id)
                if project:
                    confirmation += f"\n📁 Проект: {project['project_name']}"
                    duration_ms = (time.time() - start_time) * 1000
                    log_event(logger, "expense_added_from_text", request_id=request_id,
                             status="success", duration_ms=duration_ms, user_id=user_id,
                             amount=expense_data['amount'], category_id=category_found['category_id'],
                             category_name=category_found['name'],
                             project_id=project_id, project_name=project['project_name'])
            except Exception as e:
                duration_ms = (time.time() - start_time) * 1000
                log_error(logger, e, "get_project_error_in_text_handler", request_id=request_id,
                         duration_ms=duration_ms, user_id=user_id, project_id=project_id)
        else:
            confirmation += f"\n📊 Общие расходы"
            duration_ms = (time.time() - start_time) * 1000
            log_event(logger, "expense_added_from_text", request_id=request_id,
                     status="success", duration_ms=duration_ms, user_id=user_id,
                     amount=expense_data['amount'], category_id=category_found['category_id'],
                     category_name=category_found['name'])

        await update.message.reply_text(confirmation)
        await check_user_budget_now(context.bot, user_id, project_id)
    else:
        log_event(logger, "text_not_parsed_as_expense", request_id=request_id,
                 status="skipped", user_id=user_id, 
                 text_preview=message_text[:50], reason="parse_failed")

async def add_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Обрабатывает команду /add для начала диалога добавления расхода
    """
    track_command("add")
    track_handler_start("add_command")
    track_flow_started("add_expense")
    error_type = None
    from utils.permissions import Permission, has_permission

    try:
        user_id = update.effective_user.id
        message_text = update.message.text

        # Проверяем право добавления расхода до любой обработки
        project_id = await helpers.get_active_project_id(user_id, context)
        if not await has_permission(user_id, project_id, Permission.ADD_EXPENSE):
            await update.message.reply_text(
                "❌ У вас нет прав на добавление расходов в этом проекте.\n"
                "Роль «Наблюдатель» позволяет только просматривать данные."
            )
            return ConversationHandler.END

        # Проверяем, содержит ли команда аргументы (только для /add ...; кнопка "➕ Добавить" — без аргументов)
        if message_text.strip().startswith("/add") and len(message_text.split()) > 1:
            # Если команда содержит аргументы, обрабатываем как раньше
            expense_data = helpers.parse_add_command(message_text)

            if not expense_data:
                log_event(logger, "invalid_command_format", user_id=user_id,
                         command_text=message_text, reason="parse_failed")
                await update.message.reply_text(
                    "❌ Неверный формат команды. Используйте:\n"
                    "/add <сумма> <категория> [описание]\n"
                    "Например: /add 100 продукты хлеб и молоко"
                )
                return ConversationHandler.END

            # Ищем категорию по имени одним SQL-запросом
            category_found = await categories.get_category_by_name(
                user_id, expense_data['category'], project_id
            )

            if not category_found:
                log_event(logger, "invalid_category_in_command", user_id=user_id,
                         category=expense_data['category'], amount=expense_data['amount'],
                         reason="category_not_found")
                await update.message.reply_text(
                    f"❌ Категория '{expense_data['category']}' не найдена.\n"
                    f"Используйте команду /add без аргументов для выбора категории."
                )
                return ConversationHandler.END
            
            # Добавляем расход
            success = await excel.add_expense(
                user_id,
                expense_data['amount'],
                category_found['category_id'],
                expense_data['description'],
                project_id
            )
            
            if not success:
                await update.message.reply_text("❌ Ошибка при добавлении расхода.")
                return ConversationHandler.END

            # Отправляем подтверждение
            category_emoji = config.DEFAULT_CATEGORIES.get(category_found['name'], '📦')

            confirmation = (
                f"✅ Расход добавлен:\n"
                f"💰 Сумма: {expense_data['amount']}\n"
                f"{category_emoji} Категория: {category_found['name']}"
            )

            if expense_data['description']:
                confirmation += f"\n📝 Описание: {expense_data['description']}"
            
            # Добавляем информацию о проекте
            if project_id is not None:
                project = await projects.get_project_by_id(user_id, project_id)
                if project:
                    confirmation += f"\n📁 Проект: {project['project_name']}"
            else:
                confirmation += f"\n📊 Общие расходы"

            await update.message.reply_text(confirmation)
            await check_user_budget_now(context.bot, user_id, project_id)
            track_flow_completed("add_expense")
            return ConversationHandler.END

        # Если команда без аргументов, начинаем диалог
        await update.message.reply_text(
            "Введите сумму расхода:"
        )

        return ENTERING_AMOUNT
    except Exception as e:
        error_type = classify_error_type(e)
        log_error(logger, e, "add_command_error")
        await update.message.reply_text("❌ Ошибка при запуске добавления расхода.")
        return ConversationHandler.END
    finally:
        if error_type:
            track_handler_error("add_command", error_type)
        else:
            track_handler_success("add_command")


async def handle_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Обрабатывает ввод суммы расхода
    """
    user_id = update.effective_user.id
    text = update.message.text
    project_id = context.user_data.get('active_project_id')

    log_event(logger, "amount_input_received", user_id=user_id, 
             input_text=text, project_id=project_id)

    try:
        # Пытаемся распарсить сумму
        amount = float(text)
        
        if amount <= 0:
            log_event(logger, "invalid_amount", user_id=user_id, amount=amount, 
                     reason="amount_negative_or_zero")
            await update.message.reply_text("❌ Сумма должна быть больше нуля. Введите сумму:")
            return ENTERING_AMOUNT

        # Сохраняем сумму в контексте
        context.user_data['amount'] = amount
        
        log_event(logger, "amount_validated", user_id=user_id, amount=amount)

        # Получаем категории для пользователя и проекта
        await categories.ensure_system_categories_exist(user_id)
        cats = await categories.get_categories_for_user_project(user_id, project_id)
        
        if not cats:
            await update.message.reply_text(
                "❌ Нет доступных категорий. Создайте категорию сначала."
            )
            return ConversationHandler.END

        # Создаем inline клавиатуру с категориями
        keyboard = []
        row = []
        
        for i, cat in enumerate(cats):
            # Получаем эмодзи из конфига для системных категорий, иначе используем 📦
            emoji = config.DEFAULT_CATEGORIES.get(cat['name'], '📦')
            button_text = f"{emoji} {cat['name']}"
            
            row.append(InlineKeyboardButton(
                button_text,
                callback_data=f"cat_{cat['category_id']}"
            ))
            
            # По 2 кнопки в ряд
            if (i + 1) % 2 == 0 or i == len(cats) - 1:
                keyboard.append(row)
                row = []
        
        # Кнопка создания новой категории
        keyboard.append([InlineKeyboardButton("➕ Создать категорию", callback_data="cat_create")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            f"Сумма: {amount:.2f}\n\nВыберите категорию расхода:",
            reply_markup=reply_markup
        )

        return CHOOSING_CATEGORY

    except ValueError:
        log_event(logger, "invalid_amount_format", user_id=user_id, 
                 input_text=text, reason="not_a_number")
        await update.message.reply_text(
            "❌ Неверный формат суммы. Пожалуйста, введите число.\n"
            "Например: 100.50"
        )
        return ENTERING_AMOUNT
    except Exception as e:
        log_error(logger, e, "amount_processing_error", user_id=user_id, input_text=text)
        await update.message.reply_text("❌ Произошла ошибка. Попробуйте еще раз.")
        return ENTERING_AMOUNT


async def handle_category_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Обрабатывает выбор категории через callback query
    """
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    callback_data = query.data
    project_id = context.user_data.get('active_project_id')
    
    if callback_data == "cat_create":
        # Переходим к созданию категории
        await query.edit_message_text(
            "Введите название новой категории:"
        )
        return CREATING_CATEGORY
    
    # Извлекаем category_id из callback_data
    if not callback_data.startswith("cat_"):
        await query.edit_message_text("❌ Ошибка выбора категории.")
        return ConversationHandler.END
    
    try:
        category_id = int(callback_data.split("_")[1])
    except (ValueError, IndexError):
        await query.edit_message_text("❌ Ошибка выбора категории.")
        return ConversationHandler.END
    
    # Проверяем категорию: сначала по user_id, для общих проектов — по id без фильтра
    category = await categories.get_category_by_id(user_id, category_id)
    if not category and project_id is not None:
        # Участник проекта может выбирать категории владельца
        category = await categories.get_category_by_id_only(category_id)
    if not category:
        await query.edit_message_text("❌ Категория не найдена.")
        return ConversationHandler.END

    # Проверяем, что категория доступна для текущего проекта
    if category['project_id'] is not None and category['project_id'] != project_id:
        await query.edit_message_text("❌ Категория недоступна для этого проекта.")
        return ConversationHandler.END
    
    # Сохраняем category_id в контексте
    context.user_data['category_id'] = category_id
    context.user_data['category_name'] = category['name']
    
    amount = context.user_data.get('amount')
    log_event(logger, "category_selected", user_id=user_id, 
             category_id=category_id, category_name=category['name'], 
             amount=amount, project_id=project_id)
    
    # Обновляем сообщение и спрашиваем описание
    emoji = config.DEFAULT_CATEGORIES.get(category['name'], '📦')
    await query.edit_message_text(
        f"Сумма: {amount:.2f}\n"
        f"{emoji} Категория: {category['name']}\n\n"
        f"Введите описание расхода (или отправьте /skip, чтобы пропустить):"
    )
    
    return ENTERING_DESCRIPTION


async def handle_create_category(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Обрабатывает создание новой категории
    """
    user_id = update.effective_user.id
    category_name = update.message.text.strip()
    project_id = context.user_data.get('active_project_id')
    
    if not category_name:
        await update.message.reply_text("❌ Название категории не может быть пустым. Введите название:")
        return CREATING_CATEGORY
    
    # Создаем категорию
    result = await categories.create_category(
        user_id=user_id,
        name=category_name,
        project_id=project_id,
        is_system=False
    )
    
    if not result['success']:
        await update.message.reply_text(
            f"❌ {result['message']}\n\nПопробуйте другое название:"
        )
        return CREATING_CATEGORY
    
    # Сохраняем category_id в контексте
    context.user_data['category_id'] = result['category_id']
    context.user_data['category_name'] = result['name']
    
    amount = context.user_data.get('amount')
    log_event(logger, "category_created_and_selected", user_id=user_id,
             category_id=result['category_id'], category_name=result['name'],
             amount=amount, project_id=project_id)
    
    # Спрашиваем описание
    await update.message.reply_text(
        f"✅ Категория '{result['name']}' создана!\n\n"
        f"Сумма: {amount:.2f}\n"
        f"📦 Категория: {result['name']}\n\n"
        f"Введите описание расхода (или отправьте /skip, чтобы пропустить):"
    )
    
    return ENTERING_DESCRIPTION


async def handle_description(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Обрабатывает ввод описания расхода
    """
    track_handler_start("add_expense_handle_description")
    error_type = None
    user_id = update.effective_user.id
    text = update.message.text

    # Получаем данные из контекста
    amount = context.user_data.get('amount', 0)
    category_id = context.user_data.get('category_id')
    category_name = context.user_data.get('category_name', '')
    project_id = context.user_data.get('active_project_id')

    try:
        if not category_id:
            log_error(logger, Exception("category_id missing"), "expense_add_failed_no_category",
                     user_id=user_id, project_id=project_id, amount=amount)
            await update.message.reply_text("❌ Ошибка: категория не выбрана.")
            return ConversationHandler.END

        # Проверяем, хочет ли пользователь пропустить описание
        if text == '/skip':
            description = ""
        else:
            description = text

        # Добавляем расход
        success = await excel.add_expense(user_id, amount, category_id, description, project_id)
        
        if success:
            log_event(logger, "expense_added", user_id=user_id, project_id=project_id,
                     amount=amount, category_id=category_id, category_name=category_name,
                     has_description=bool(description))
        else:
            log_error(logger, Exception("Failed to add expense"), "expense_add_failed",
                     user_id=user_id, project_id=project_id, amount=amount, 
                     category_id=category_id, category_name=category_name)

        # Отправляем подтверждение
        emoji = config.DEFAULT_CATEGORIES.get(category_name, '📦')

        confirmation = (
            f"✅ Расход добавлен:\n"
            f"💰 Сумма: {amount:.2f}\n"
            f"{emoji} Категория: {category_name}"
        )

        if description:
            confirmation += f"\n📝 Описание: {description}"
        
        # Добавляем информацию о проекте
        if project_id is not None:
            project = await projects.get_project_by_id(user_id, project_id)
            if project:
                confirmation += f"\n📁 Проект: {project['project_name']}"
        else:
            confirmation += f"\n📊 Общие расходы"

        await update.message.reply_text(confirmation, reply_markup=helpers.get_main_menu_keyboard())

        if success:
            await check_user_budget_now(context.bot, user_id, project_id)
            track_flow_completed("add_expense")

            # Проверяем паттерн постоянного расхода — неблокирующая фоновая задача.
            # Запускаем только если есть описание (без него паттерн не определить).
            if description:
                from handlers.recurring import suggest_recurring_if_pattern
                asyncio.create_task(
                    suggest_recurring_if_pattern(
                        context.bot,
                        str(user_id),
                        project_id,
                        category_id,
                        description,
                        context.bot_data,
                    )
                )

        # Очищаем данные пользователя
        for key in ['amount', 'category_id', 'category_name']:
            context.user_data.pop(key, None)

        return ConversationHandler.END
    except Exception as e:
        error_type = classify_error_type(e)
        log_error(logger, e, "handle_description_error", user_id=user_id, project_id=project_id)
        await update.message.reply_text("❌ Ошибка при добавлении расхода. Попробуйте снова.")
        return ConversationHandler.END
    finally:
        if error_type:
            track_handler_error("add_expense_handle_description", error_type)
        else:
            track_handler_success("add_expense_handle_description")


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Отменяет диалог добавления расхода
    """
    track_handler_start("add_expense_cancel")
    error_type = None
    # Очищаем данные пользователя
    try:
        for key in ['amount', 'category_id', 'category_name']:
            context.user_data.pop(key, None)
        track_flow_cancelled("add_expense")
        return await helpers.cancel_conversation(update, context, "Добавление расхода отменено.")
    except Exception as e:
        error_type = classify_error_type(e)
        log_error(logger, e, "cancel_expense_error")
        await update.message.reply_text("❌ Не удалось отменить добавление расхода.")
        return ConversationHandler.END
    finally:
        if error_type:
            track_handler_error("add_expense_cancel", error_type)
        else:
            track_handler_success("add_expense_cancel")


async def direct_amount_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Обрабатывает прямой ввод суммы без команды
    """
    from utils.permissions import Permission, has_permission

    user_id = update.effective_user.id
    text = update.message.text
    project_id = await helpers.get_active_project_id(user_id, context)

    # Проверяем право добавления расхода до показа категорий
    if not await has_permission(user_id, project_id, Permission.ADD_EXPENSE):
        await update.message.reply_text(
            "❌ У вас нет прав на добавление расходов в этом проекте.\n"
            "Роль «Наблюдатель» позволяет только просматривать данные."
        )
        return ConversationHandler.END

    # Проверяем, похоже ли сообщение на сумму
    try:
        # Пытаемся распарсить как число
        amount = float(text)
        
        if amount <= 0:
            return ConversationHandler.END

        # Сохраняем сумму в контексте
        context.user_data['amount'] = amount

        # Получаем категории для пользователя и проекта
        await categories.ensure_system_categories_exist(user_id)
        cats = await categories.get_categories_for_user_project(user_id, project_id)
        
        if not cats:
            await update.message.reply_text(
                "❌ Нет доступных категорий. Создайте категорию сначала."
            )
            return ConversationHandler.END

        # Создаем inline клавиатуру с категориями
        keyboard = []
        row = []
        
        for i, cat in enumerate(cats):
            emoji = config.DEFAULT_CATEGORIES.get(cat['name'], '📦')
            button_text = f"{emoji} {cat['name']}"
            
            row.append(InlineKeyboardButton(
                button_text,
                callback_data=f"cat_{cat['category_id']}"
            ))
            
            if (i + 1) % 2 == 0 or i == len(cats) - 1:
                keyboard.append(row)
                row = []
        
        keyboard.append([InlineKeyboardButton("➕ Создать категорию", callback_data="cat_create")])
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            f"Сумма: {amount:.2f}\n\nВыберите категорию расхода:",
            reply_markup=reply_markup
        )

        return CHOOSING_CATEGORY

    except ValueError:
        # Если не удалось распарсить как число, значит это не сумма
        return ConversationHandler.END


def register_expense_handlers(application):
    """
    Регистрирует обработчики команд для добавления расходов
    """
    # Регистрируем ConversationHandler для команды /add
    add_conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("add", add_command),
            MessageHandler(filters.Regex(main_menu_button_regex("add")), add_command),
            MessageHandler(filters.Regex(r'^\d+(\.\d+)?$') & ~filters.COMMAND, direct_amount_handler)
        ],
        states={
            ENTERING_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_amount)],
            CHOOSING_CATEGORY: [CallbackQueryHandler(handle_category_callback, pattern=r'^cat_')],
            CREATING_CATEGORY: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_create_category)],
            ENTERING_DESCRIPTION: [
                CommandHandler("skip", handle_description),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_description)
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        # Важно: устанавливаем name, чтобы избежать конфликтов с другими ConversationHandler
        name="add_expense_conversation",
        # Устанавливаем persistent=False, чтобы разговор не сохранялся между перезапусками
        persistent=False
    )
    application.add_handler(add_conv_handler)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
