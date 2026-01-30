"""
Обработчики команд для добавления расходов
"""

from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import ContextTypes, CommandHandler, filters, MessageHandler, ConversationHandler
from utils import excel, helpers, projects
from utils.helpers import main_menu_button_regex
from utils.logger import get_logger, log_command, log_event, log_error
import config

logger = get_logger("handlers.expense")

# Состояния для ConversationHandler
ENTERING_AMOUNT, CHOOSING_CATEGORY, ENTERING_DESCRIPTION = range(3)


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
        # Проверяем, что категория существует
        if expense_data['category'] not in config.DEFAULT_CATEGORIES:
            log_event(logger, "invalid_category_in_text", user_id=user_id, 
                     category=expense_data['category'], 
                     message="Category not found in text message")
            return  # Не отвечаем, если категория не найдена в обычном сообщении

        # Получаем активный проект
        project_id = context.user_data.get('active_project_id')
        
        log_event(logger, "expense_parsed_from_text", user_id=user_id, 
                 amount=expense_data['amount'], category=expense_data['category'],
                 has_description=bool(expense_data['description']), project_id=project_id)
        
        # Добавляем расход
        success = await excel.add_expense(
            user_id,
            expense_data['amount'],
            expense_data['category'],
            expense_data['description'],
            project_id
        )

        if not success:
            duration_ms = (time.time() - start_time) * 1000
            log_error(logger, Exception("Failed to add expense from text"), 
                     "expense_add_failed_from_text", request_id=request_id,
                     duration_ms=duration_ms, user_id=user_id,
                     amount=expense_data['amount'], category=expense_data['category'])
            await update.message.reply_text("❌ Ошибка при добавлении расхода. Попробуйте еще раз.")
            return

        # Отправляем подтверждение
        category_emoji = config.DEFAULT_CATEGORIES[expense_data['category']]

        confirmation = (
            f"✅ Расход добавлен:\n"
            f"💰 Сумма: {expense_data['amount']}\n"
            f"{category_emoji} Категория: {expense_data['category'].title()}"
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
                             amount=expense_data['amount'], category=expense_data['category'],
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
                     amount=expense_data['amount'], category=expense_data['category'])

        await update.message.reply_text(confirmation)
    else:
        log_event(logger, "text_not_parsed_as_expense", request_id=request_id,
                 status="skipped", user_id=user_id, 
                 text_preview=message_text[:50], reason="parse_failed")

async def add_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Обрабатывает команду /add для начала диалога добавления расхода
    """
    user_id = update.effective_user.id
    message_text = update.message.text

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

        # Проверяем, что категория существует
        if expense_data['category'] not in config.DEFAULT_CATEGORIES:
            categories_list = ", ".join(config.DEFAULT_CATEGORIES.keys())
            log_event(logger, "invalid_category_in_command", user_id=user_id,
                     category=expense_data['category'], amount=expense_data['amount'],
                     reason="category_not_found")
            await update.message.reply_text(
                f"❌ Категория '{expense_data['category']}' не найдена.\n"
                f"Доступные категории: {categories_list}"
            )
            return ConversationHandler.END

        # Получаем активный проект
        project_id = context.user_data.get('active_project_id')
        
        # Добавляем расход
        await excel.add_expense(
            user_id,
            expense_data['amount'],
            expense_data['category'],
            expense_data['description'],
            project_id
        )

        # Отправляем подтверждение
        category_emoji = config.DEFAULT_CATEGORIES[expense_data['category']]

        confirmation = (
            f"✅ Расход добавлен:\n"
            f"💰 Сумма: {expense_data['amount']}\n"
            f"{category_emoji} Категория: {expense_data['category']}"
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
        return ConversationHandler.END

    # Если команда без аргументов, начинаем диалог
    await update.message.reply_text(
        "Введите сумму расхода:"
    )

    return ENTERING_AMOUNT


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

        # Отправляем клавиатуру с категориями
        keyboard = []
        row = []
        for i, category in enumerate(config.DEFAULT_CATEGORIES.keys()):
            emoji = config.DEFAULT_CATEGORIES[category]
            row.append(f"{emoji} {category}")
            # По 2 категории в ряд
            if (i + 1) % 2 == 0 or i == len(config.DEFAULT_CATEGORIES) - 1:
                keyboard.append(row)
                row = []

        keyboard.append(['Отмена'])
        reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)

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


async def handle_category(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Обрабатывает выбор категории расхода
    """
    user_id = update.effective_user.id
    text = update.message.text

    if text == 'Отмена':
        from utils.helpers import get_main_menu_keyboard
        await update.message.reply_text(
            "Добавление расхода отменено.",
            reply_markup=get_main_menu_keyboard()
        )
        return ConversationHandler.END

    # Извлекаем категорию из текста (убираем эмодзи)
    category = text.split()[-1].lower()

    # Проверяем, что категория существует
    if category not in config.DEFAULT_CATEGORIES:
        amount = context.user_data.get('amount')
        log_event(logger, "invalid_category_selected", user_id=user_id,
                 category=category, amount=amount, input_text=text,
                 reason="category_not_in_list")
        categories_list = ", ".join(config.DEFAULT_CATEGORIES.keys())
        await update.message.reply_text(
            f"❌ Категория '{category}' не найдена.\n"
            f"Доступные категории: {categories_list}"
        )
        return CHOOSING_CATEGORY

    # Сохраняем категорию в контексте
    amount = context.user_data.get('amount')
    project_id = context.user_data.get('active_project_id')
    context.user_data['category'] = category
    
    log_event(logger, "category_validated", user_id=user_id, category=category, amount=amount, project_id=project_id)

    # Спрашиваем описание
    await update.message.reply_text(
        "Введите описание расхода (или отправьте /skip, чтобы пропустить):"
    )

    return ENTERING_DESCRIPTION


async def handle_description(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Обрабатывает ввод описания расхода
    """
    user_id = update.effective_user.id
    text = update.message.text

    # Получаем данные из контекста
    amount = context.user_data.get('amount', 0)
    category = context.user_data.get('category', '')
    project_id = context.user_data.get('active_project_id')

    # Проверяем, хочет ли пользователь пропустить описание
    if text == '/skip':
        description = ""
    else:
        description = text

    # Добавляем расход
    success = await excel.add_expense(user_id, amount, category, description, project_id)
    
    if success:
        log_event(logger, "expense_added", user_id=user_id, project_id=project_id,
                 amount=amount, category=category, has_description=bool(description))
    else:
        log_error(logger, Exception("Failed to add expense"), "expense_add_failed",
                 user_id=user_id, project_id=project_id, amount=amount, category=category)

    # Отправляем подтверждение
    category_emoji = config.DEFAULT_CATEGORIES[category]

    confirmation = (
        f"✅ Расход добавлен:\n"
        f"💰 Сумма: {amount:.2f}\n"
        f"{category_emoji} Категория: {category}"
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

    # Очищаем данные пользователя
    # context.user_data.clear()
    for key in ['amount', 'category']:
        context.user_data.pop(key, None)

    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Отменяет диалог добавления расхода
    """
    # Очищаем данные пользователя
    for key in ['amount', 'category']:
        context.user_data.pop(key, None)
    
    return await helpers.cancel_conversation(update, context, "Добавление расхода отменено.")


async def direct_amount_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Обрабатывает прямой ввод суммы без команды
    """
    user_id = update.effective_user.id
    text = update.message.text

    # Проверяем, похоже ли сообщение на сумму
    try:
        # Пытаемся распарсить как число
        amount = float(text)

        # Сохраняем сумму в контексте
        context.user_data['amount'] = amount

        # Отправляем клавиатуру с категориями
        keyboard = []
        row = []
        for i, category in enumerate(config.DEFAULT_CATEGORIES.keys()):
            emoji = config.DEFAULT_CATEGORIES[category]
            row.append(f"{emoji} {category}")
            # По 2 категории в ряд
            if (i + 1) % 2 == 0 or i == len(config.DEFAULT_CATEGORIES) - 1:
                keyboard.append(row)
                row = []

        keyboard.append(['Отмена'])
        reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)

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
            CHOOSING_CATEGORY: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_category)],
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
