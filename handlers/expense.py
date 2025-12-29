"""
Обработчики команд для добавления расходов
"""

from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import ContextTypes, CommandHandler, filters, MessageHandler, ConversationHandler
from utils import excel, helpers
import config

# Состояния для ConversationHandler
ENTERING_AMOUNT, CHOOSING_CATEGORY, ENTERING_DESCRIPTION = range(3)


async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Обрабатывает текстовые сообщения, пытаясь распознать добавление расхода
    """
    user_id = update.effective_user.id
    message_text = update.message.text

    # Пытаемся распарсить как команду добавления расхода
    expense_data = helpers.parse_add_command(message_text)

    if expense_data:
        # Проверяем, что категория существует
        if expense_data['category'] not in config.DEFAULT_CATEGORIES:
            return  # Не отвечаем, если категория не найдена в обычном сообщении

        # Получаем активный проект
        project_id = context.user_data.get('active_project_id')
        print('project_id:', project_id)
        print('user_id', user_id)
        
        # Добавляем расход
        excel.add_expense(
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
            f"{category_emoji} Категория: {expense_data['category'].title()}"
        )

        if expense_data['description']:
            confirmation += f"\n📝 Описание: {expense_data['description'].title()}"
        
        # Добавляем информацию о проекте
        if project_id is not None:
            from utils import projects
            project = projects.get_project_by_id(user_id, project_id)
            if project:
                confirmation += f"\n📁 Проект: {project['project_name']}"
        else:
            confirmation += f"\n📊 Общие расходы"

        update.message.reply_text(confirmation)

async def add_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Обрабатывает команду /add для начала диалога добавления расхода
    """
    user_id = update.effective_user.id
    message_text = update.message.text

    # Проверяем, содержит ли команда аргументы
    if len(message_text.split()) > 1:
        # Если команда содержит аргументы, обрабатываем как раньше
        expense_data = helpers.parse_add_command(message_text)

        if not expense_data:
            update.message.reply_text(
                "❌ Неверный формат команды. Используйте:\n"
                "/add <сумма> <категория> [описание]\n"
                "Например: /add 100 продукты хлеб и молоко"
            )
            return ConversationHandler.END

        # Проверяем, что категория существует
        if expense_data['category'] not in config.DEFAULT_CATEGORIES:
            categories_list = ", ".join(config.DEFAULT_CATEGORIES.keys())
            update.message.reply_text(
                f"❌ Категория '{expense_data['category']}' не найдена.\n"
                f"Доступные категории: {categories_list}"
            )
            return ConversationHandler.END

        # Получаем активный проект
        project_id = context.user_data.get('active_project_id')
        
        # Добавляем расход
        excel.add_expense(
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
            from utils import projects
            project = projects.get_project_by_id(user_id, project_id)
            if project:
                confirmation += f"\n📁 Проект: {project['project_name']}"
        else:
            confirmation += f"\n📊 Общие расходы"

        update.message.reply_text(confirmation)
        return ConversationHandler.END

    # Если команда без аргументов, начинаем диалог
    update.message.reply_text(
        "Введите сумму расхода:"
    )

    return ENTERING_AMOUNT


async def handle_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Обрабатывает ввод суммы расхода
    """
    user_id = update.effective_user.id
    text = update.message.text

    try:
        # Пытаемся распарсить сумму
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

        update.message.reply_text(
            f"Сумма: {amount:.2f}\n\nВыберите категорию расхода:",
            reply_markup=reply_markup
        )

        return CHOOSING_CATEGORY

    except ValueError:
        # Если не удалось распарсить сумму, просим ввести снова
        update.message.reply_text(
            "❌ Неверный формат суммы. Пожалуйста, введите число.\n"
            "Например: 100.50"
        )
        return ENTERING_AMOUNT


async def handle_category(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Обрабатывает выбор категории расхода
    """
    user_id = update.effective_user.id
    text = update.message.text

    if text == 'Отмена':
        update.message.reply_text(
            "Добавление расхода отменено.",
            reply_markup=ReplyKeyboardRemove()
        )
        return ConversationHandler.END

    # Извлекаем категорию из текста (убираем эмодзи)
    category = text.split()[-1].lower()

    # Проверяем, что категория существует
    if category not in config.DEFAULT_CATEGORIES:
        categories_list = ", ".join(config.DEFAULT_CATEGORIES.keys())
        update.message.reply_text(
            f"❌ Категория '{category}' не найдена.\n"
            f"Доступные категории: {categories_list}"
        )
        return CHOOSING_CATEGORY

    # Сохраняем категорию в контексте
    context.user_data['category'] = category

    # Спрашиваем описание
    update.message.reply_text(
        "Введите описание расхода (или отправьте /skip, чтобы пропустить):",
        reply_markup=ReplyKeyboardRemove()
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
    excel.add_expense(user_id, amount, category, description, project_id)

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
        from utils import projects
        project = projects.get_project_by_id(user_id, project_id)
        if project:
            confirmation += f"\n📁 Проект: {project['project_name']}"
    else:
        confirmation += f"\n📊 Общие расходы"

    update.message.reply_text(confirmation)

    # Очищаем данные пользователя
    context.user_data.clear()

    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Отменяет диалог добавления расхода
    """
    update.message.reply_text(
        "Добавление расхода отменено.",
        reply_markup=ReplyKeyboardRemove()
    )

    # Очищаем данные пользователя
    context.user_data.clear()

    return ConversationHandler.END


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

        update.message.reply_text(
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
