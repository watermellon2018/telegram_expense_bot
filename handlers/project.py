"""
Обработчики команд для работы с проектами
"""

from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.constants import ParseMode
from telegram.ext import ContextTypes, CommandHandler, filters, MessageHandler, ConversationHandler
from utils import projects
import config

# Состояния для ConversationHandler
CONFIRMING_DELETE, ENTERING_PROJECT_NAME, ENTERING_PROJECT_TO_SELECT, ENTERING_PROJECT_TO_DELETE = range(4)


async def project_create_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Обрабатывает команду /project_create для создания нового проекта
    """
    user_id = update.effective_user.id
    message_text = update.message.text
    
    # Проверяем, содержит ли команда название проекта
    parts = message_text.split(maxsplit=1)
    
    if len(parts) < 2:
        update.message.reply_text(
            "❌ Укажите название проекта.\n"
            "Используйте: /project_create <название>\n"
            "Например: /project_create Отпуск"
        )
        return
    
    project_name = parts[1].strip()
    
    # Создаем проект
    result = projects.create_project(user_id, project_name)
    
    if result['success']:
        # Автоматически переключаемся на созданный проект
        set_result = projects.set_active_project(user_id, result['project_id'])
        
        # Сохраняем в контексте пользователя
        context.user_data['active_project_id'] = result['project_id']
        
        update.message.reply_text(
            f"✅ {result['message']}\n"
            f"📁 Проект '{project_name}' активирован\n\n"
            f"Теперь все расходы будут записываться в этот проект."
        )
    else:
        update.message.reply_text(f"❌ {result['message']}")


async def project_list_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Обрабатывает команду /project_list для отображения списка проектов
    """
    user_id = update.effective_user.id
    
    # Получаем список проектов
    all_projects = projects.get_all_projects(user_id)
    
    if not all_projects:
        update.message.reply_text(
            "📋 У вас пока нет проектов.\n\n"
            "Создайте проект командой:\n"
            "/project_create <название>"
        )
        return
    
    # Получаем активный проект
    active_project = projects.get_active_project(user_id)
    active_project_id = active_project['project_id'] if active_project else None
    
    # Формируем список
    message = "📋 Ваши проекты:\n\n"
    
    for project in all_projects:
        project_id = project['project_id']
        project_name = project['project_name']
        created_date = project['created_date']
        
        # Получаем статистику по проекту
        stats = projects.get_project_stats(user_id, project_id)
        
        # Отмечаем активный проект
        if project_id == active_project_id:
            message += f"📁 *{project_name}* (активен)\n"
        else:
            message += f"📁 {project_name}\n"
        
        message += f"   ID: {project_id}\n"
        message += f"   Создан: {created_date}\n"
        message += f"   Расходов: {stats['count']}\n"
        message += f"   Сумма: {stats['total']:.2f}\n\n"
    
    # Показываем текущий режим
    if active_project_id is None:
        message += "📊 Текущий режим: Общие расходы"
    else:
        message += f"📁 Текущий режим: Проект '{active_project['project_name']}'"
    
    update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN)


async def project_select_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Обрабатывает команду /project_select для переключения на проект
    """
    user_id = update.effective_user.id
    message_text = update.message.text
    
    # Проверяем, содержит ли команда название или ID проекта
    parts = message_text.split(maxsplit=1)
    
    if len(parts) < 2:
        update.message.reply_text(
            "❌ Укажите название или ID проекта.\n"
            "Используйте: /project_select <название или ID>\n"
            "Например: /project_select Отпуск\n"
            "Или: /project_select 1"
        )
        return
    
    project_identifier = parts[1].strip()
    
    # Пытаемся найти проект по ID или названию
    project = None
    
    # Проверяем, является ли идентификатор числом (ID)
    if project_identifier.isdigit():
        project = projects.get_project_by_id(user_id, int(project_identifier))
    
    # Если не нашли по ID, ищем по названию
    if project is None:
        project = projects.get_project_by_name(user_id, project_identifier)
    
    if project is None:
        update.message.reply_text(
            f"❌ Проект '{project_identifier}' не найден.\n\n"
            f"Посмотрите список проектов: /project_list"
        )
        return
    
    # Переключаемся на проект
    result = projects.set_active_project(user_id, project['project_id'])
    
    if result['success']:
        # Сохраняем в контексте пользователя
        context.user_data['active_project_id'] = project['project_id']
        
        update.message.reply_text(
            f"✅ {result['message']}\n\n"
            f"Теперь все расходы будут записываться в проект '{project['project_name']}'."
        )
    else:
        update.message.reply_text(f"❌ {result['message']}")


async def project_main_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Обрабатывает команду /project_main для переключения на общие расходы
    """
    user_id = update.effective_user.id
    
    # Переключаемся на общие расходы
    result = projects.set_active_project(user_id, None)
    
    if result['success']:
        # Сбрасываем в контексте пользователя
        context.user_data['active_project_id'] = None
        
        update.message.reply_text(
            f"✅ {result['message']}\n\n"
            f"Теперь все расходы будут записываться в общие расходы."
        )
    else:
        update.message.reply_text(f"❌ {result['message']}")


async def project_delete_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Начинает процесс удаления проекта
    """
    user_id = update.effective_user.id
    message_text = update.message.text
    
    # Проверяем, содержит ли команда название или ID проекта
    parts = message_text.split(maxsplit=1)
    
    if len(parts) < 2:
        update.message.reply_text(
            "❌ Укажите название или ID проекта.\n"
            "Используйте: /project_delete <название или ID>\n"
            "Например: /project_delete Отпуск\n"
            "Или: /project_delete 1"
        )
        return ConversationHandler.END
    
    project_identifier = parts[1].strip()
    
    # Пытаемся найти проект по ID или названию
    project = None
    
    # Проверяем, является ли идентификатор числом (ID)
    if project_identifier.isdigit():
        project = projects.get_project_by_id(user_id, int(project_identifier))
    
    # Если не нашли по ID, ищем по названию
    if project is None:
        project = projects.get_project_by_name(user_id, project_identifier)
    
    if project is None:
        update.message.reply_text(
            f"❌ Проект '{project_identifier}' не найден.\n\n"
            f"Посмотрите список проектов: /project_list"
        )
        return ConversationHandler.END
    
    # Сохраняем ID проекта в контексте
    context.user_data['delete_project_id'] = project['project_id']
    context.user_data['delete_project_name'] = project['project_name']
    
    # Получаем статистику по проекту
    stats = projects.get_project_stats(user_id, project['project_id'])
    
    # Создаем клавиатуру для подтверждения
    keyboard = [['Да, удалить', 'Отмена']]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    
    update.message.reply_text(
        f"⚠️ Вы уверены, что хотите удалить проект '{project['project_name']}'?\n\n"
        f"Будет удалено:\n"
        f"- Расходов: {stats['count']}\n"
        f"- На сумму: {stats['total']:.2f}\n\n"
        f"Это действие нельзя отменить!",
        reply_markup=reply_markup
    )
    
    return CONFIRMING_DELETE


async def project_delete_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Подтверждает удаление проекта
    """
    user_id = update.effective_user.id
    text = update.message.text
    
    if text == 'Да, удалить':
        # Получаем ID проекта из контекста
        project_id = context.user_data.get('delete_project_id')
        project_name = context.user_data.get('delete_project_name')
        
        if project_id is None:
            update.message.reply_text(
                "❌ Ошибка: проект не найден.",
                reply_markup=ReplyKeyboardRemove()
            )
            return ConversationHandler.END
        
        # Удаляем проект
        result = projects.delete_project(user_id, project_id)
        
        if result['success']:
            # Если удаленный проект был активным, сбрасываем контекст
            if context.user_data.get('active_project_id') == project_id:
                context.user_data['active_project_id'] = None
            
            update.message.reply_text(
                f"✅ {result['message']}\n\n"
                f"Все данные проекта '{project_name}' удалены.",
                reply_markup=ReplyKeyboardRemove()
            )
        else:
            update.message.reply_text(
                f"❌ {result['message']}",
                reply_markup=ReplyKeyboardRemove()
            )
    else:
        update.message.reply_text(
            "Удаление проекта отменено.",
            reply_markup=ReplyKeyboardRemove()
        )
    
    # Очищаем данные пользователя
    context.user_data.pop('delete_project_id', None)
    context.user_data.pop('delete_project_name', None)
    
    return ConversationHandler.END


async def project_delete_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Отменяет удаление проекта
    """
    update.message.reply_text(
        "Удаление проекта отменено.",
        reply_markup=ReplyKeyboardRemove()
    )
    
    # Очищаем данные пользователя
    context.user_data.pop('delete_project_id', None)
    context.user_data.pop('delete_project_name', None)
    
    return ConversationHandler.END


async def project_info_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Обрабатывает команду /project_info для отображения информации о текущем проекте
    """
    user_id = update.effective_user.id
    
    # Получаем активный проект
    active_project = projects.get_active_project(user_id)
    
    if active_project is None:
        update.message.reply_text(
            "📊 Текущий режим: Общие расходы\n\n"
            "Все расходы записываются в общую базу.\n\n"
            "Чтобы переключиться на проект, используйте:\n"
            "/project_select <название или ID>"
        )
        return
    
    # Получаем статистику по проекту
    stats = projects.get_project_stats(user_id, active_project['project_id'])
    
    message = f"📁 Текущий проект: {active_project['project_name']}\n\n"
    message += f"ID: {active_project['project_id']}\n"
    message += f"Создан: {active_project['created_date']}\n"
    message += f"Расходов: {stats['count']}\n"
    message += f"Общая сумма: {stats['total']:.2f}\n\n"
    
    if stats['by_category']:
        message += "По категориям:\n"
        for category, amount in sorted(stats['by_category'].items(), key=lambda x: x[1], reverse=True):
            emoji = config.DEFAULT_CATEGORIES.get(category, '📦')
            message += f"{emoji} {category.title()}: {amount:.2f}\n"
    
    update.message.reply_text(message)


# Интерактивные обработчики для кнопок меню

async def button_create_project_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Начинает процесс создания проекта через кнопку
    """
    update.message.reply_text(
        "🆕 Создание проекта\n\n"
        "Введите название проекта:\n"
        "Например: Отпуск\n\n"
        "Или нажмите /cancel для отмены",
        reply_markup=ReplyKeyboardRemove()
    )
    return ENTERING_PROJECT_NAME

async def button_create_project_finish(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Завершает создание проекта
    """
    user_id = update.effective_user.id
    project_name = update.message.text.strip()
    
    # Создаем проект
    result = projects.create_project(user_id, project_name)
    
    if result['success']:
        # Автоматически переключаемся на созданный проект
        projects.set_active_project(user_id, result['project_id'])
        context.user_data['active_project_id'] = result['project_id']
        
        # Возвращаем меню проектов
        keyboard = [
            ['🆕 Создать проект', '📋 Список проектов'],
            ['🔄 Выбрать проект', '📊 Общие расходы'],
            ['ℹ️ Инфо о проекте', '🗑️ Удалить проект'],
            ['⬅️ Главное меню']
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        
        update.message.reply_text(
            f"✅ {result['message']}\n"
            f"📁 Проект '{project_name}' активирован\n\n"
            f"Теперь все расходы будут записываться в этот проект.",
            reply_markup=reply_markup
        )
    else:
        update.message.reply_text(f"❌ {result['message']}")
    
    return ConversationHandler.END

async def button_select_project_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Начинает процесс выбора проекта
    """
    user_id = update.effective_user.id
    
    # Получаем список проектов
    all_projects = projects.get_all_projects(user_id)
    
    if not all_projects:
        update.message.reply_text(
            "📋 У вас пока нет проектов.\n\n"
            "Создайте проект с помощью кнопки '🆕 Создать проект'"
        )
        return ConversationHandler.END
    
    # Формируем список
    message = "🔄 Выбор проекта\n\nВаши проекты:\n\n"
    for project in all_projects:
        message += f"{project['project_id']}. {project['project_name']}\n"
    
    message += "\nВведите название или ID проекта:\nИли нажмите /cancel для отмены"
    
    update.message.reply_text(message, reply_markup=ReplyKeyboardRemove())
    return ENTERING_PROJECT_TO_SELECT

async def button_select_project_finish(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Завершает выбор проекта
    """
    user_id = update.effective_user.id
    project_identifier = update.message.text.strip()
    
    # Пытаемся найти проект
    project = None
    if project_identifier.isdigit():
        project = projects.get_project_by_id(user_id, int(project_identifier))
    if project is None:
        project = projects.get_project_by_name(user_id, project_identifier)
    
    # Возвращаем меню проектов
    keyboard = [
        ['🆕 Создать проект', '📋 Список проектов'],
        ['🔄 Выбрать проект', '📊 Общие расходы'],
        ['ℹ️ Инфо о проекте', '🗑️ Удалить проект'],
        ['⬅️ Главное меню']
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
    if project is None:
        update.message.reply_text(
            f"❌ Проект '{project_identifier}' не найден.",
            reply_markup=reply_markup
        )
    else:
        # Переключаемся на проект
        result = projects.set_active_project(user_id, project['project_id'])
        context.user_data['active_project_id'] = project['project_id']
        
        update.message.reply_text(
            f"✅ {result['message']}\n\n"
            f"Теперь все расходы будут записываться в проект '{project['project_name']}'.",
            reply_markup=reply_markup
        )
    
    return ConversationHandler.END

async def button_delete_project_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Начинает процесс удаления проекта
    """
    user_id = update.effective_user.id
    
    # Получаем список проектов
    all_projects = projects.get_all_projects(user_id)
    
    if not all_projects:
        update.message.reply_text(
            "📋 У вас пока нет проектов."
        )
        return ConversationHandler.END
    
    # Формируем список
    message = "🗑️ Удаление проекта\n\nВаши проекты:\n\n"
    for project in all_projects:
        message += f"{project['project_id']}. {project['project_name']}\n"
    
    message += "\nВведите название или ID проекта для удаления:\nИли нажмите /cancel для отмены"
    
    update.message.reply_text(message, reply_markup=ReplyKeyboardRemove())
    return ENTERING_PROJECT_TO_DELETE

async def button_delete_project_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Запрашивает подтверждение удаления
    """
    user_id = update.effective_user.id
    project_identifier = update.message.text.strip()
    
    # Пытаемся найти проект
    project = None
    if project_identifier.isdigit():
        project = projects.get_project_by_id(user_id, int(project_identifier))
    if project is None:
        project = projects.get_project_by_name(user_id, project_identifier)
    
    if project is None:
        # Возвращаем меню проектов
        keyboard = [
            ['🆕 Создать проект', '📋 Список проектов'],
            ['🔄 Выбрать проект', '📊 Общие расходы'],
            ['ℹ️ Инфо о проекте', '🗑️ Удалить проект'],
            ['⬅️ Главное меню']
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        update.message.reply_text(
            f"❌ Проект '{project_identifier}' не найден.",
            reply_markup=reply_markup
        )
        return ConversationHandler.END
    
    # Сохраняем ID проекта в контексте
    context.user_data['delete_project_id'] = project['project_id']
    context.user_data['delete_project_name'] = project['project_name']
    
    # Получаем статистику
    stats = projects.get_project_stats(user_id, project['project_id'])
    
    # Создаем клавиатуру для подтверждения
    keyboard = [['Да, удалить', 'Отмена']]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    
    update.message.reply_text(
        f"⚠️ Вы уверены, что хотите удалить проект '{project['project_name']}'?\n\n"
        f"Будет удалено:\n"
        f"- Расходов: {stats['count']}\n"
        f"- На сумму: {stats['total']:.2f}\n\n"
        f"Это действие нельзя отменить!",
        reply_markup=reply_markup
    )
    
    return CONFIRMING_DELETE

async def button_delete_project_finish(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Завершает удаление проекта
    """
    user_id = update.effective_user.id
    text = update.message.text
    
    # Возвращаем меню проектов
    keyboard = [
        ['🆕 Создать проект', '📋 Список проектов'],
        ['🔄 Выбрать проект', '📊 Общие расходы'],
        ['ℹ️ Инфо о проекте', '🗑️ Удалить проект'],
        ['⬅️ Главное меню']
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
    if text == 'Да, удалить':
        project_id = context.user_data.get('delete_project_id')
        project_name = context.user_data.get('delete_project_name')
        
        if project_id is None:
            update.message.reply_text(
                "❌ Ошибка: проект не найден.",
                reply_markup=reply_markup
            )
            return ConversationHandler.END
        
        # Удаляем проект
        result = projects.delete_project(user_id, project_id)
        
        if result['success']:
            # Если удаленный проект был активным, сбрасываем контекст
            if context.user_data.get('active_project_id') == project_id:
                context.user_data['active_project_id'] = None
            
            update.message.reply_text(
                f"✅ {result['message']}\n\n"
                f"Все данные проекта '{project_name}' удалены.",
                reply_markup=reply_markup
            )
        else:
            update.message.reply_text(
                f"❌ {result['message']}",
                reply_markup=reply_markup
            )
    else:
        update.message.reply_text(
            "Удаление проекта отменено.",
            reply_markup=reply_markup
        )
    
    # Очищаем данные
    context.user_data.pop('delete_project_id', None)
    context.user_data.pop('delete_project_name', None)
    
    return ConversationHandler.END

async def conversation_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Отменяет текущий диалог
    """
    # Возвращаем меню проектов
    keyboard = [
        ['🆕 Создать проект', '📋 Список проектов'],
        ['🔄 Выбрать проект', '📊 Общие расходы'],
        ['ℹ️ Инфо о проекте', '🗑️ Удалить проект'],
        ['⬅️ Главное меню']
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
    update.message.reply_text(
        "Действие отменено.",
        reply_markup=reply_markup
    )
    return ConversationHandler.END


def register_project_handlers(application):
    """
    Регистрирует обработчики команд для работы с проектами
    """
    # Регистрируем команды
    application.add_handler(CommandHandler("project_create", project_create_command))
    application.add_handler(CommandHandler("project_list", project_list_command))
    application.add_handler(CommandHandler("project_select", project_select_command))
    application.add_handler(CommandHandler("project_main", project_main_command))
    application.add_handler(CommandHandler("project_info", project_info_command))
    
    # Регистрируем ConversationHandler для удаления проекта (команда)
    delete_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("project_delete", project_delete_start)],
        states={
            CONFIRMING_DELETE: [MessageHandler(filters.TEXT & ~filters.COMMAND, project_delete_confirm)],
        },
        fallbacks=[CommandHandler("cancel", project_delete_cancel)],
        name="delete_project_conversation",
        persistent=False
    )
    application.add_handler(delete_conv_handler)
    
    # Регистрируем обработчики для кнопок меню
    
    # Кнопка "Список проектов"
    application.add_handler(MessageHandler(filters.Regex('^📋 Список проектов$'), project_list_command))
    
    # Кнопка "Общие расходы"
    application.add_handler(MessageHandler(filters.Regex('^📊 Общие расходы$'), project_main_command))
    
    # Кнопка "Инфо о проекте"
    application.add_handler(MessageHandler(filters.Regex('^ℹ️ Инфо о проекте$'), project_info_command))
    
    # ConversationHandler для создания проекта (кнопка)
    create_conv_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex('^🆕 Создать проект$'), button_create_project_start)],
        states={
            ENTERING_PROJECT_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, button_create_project_finish)],
        },
        fallbacks=[CommandHandler("cancel", conversation_cancel)],
        name="create_project_button_conversation",
        persistent=False
    )
    application.add_handler(create_conv_handler)
    
    # ConversationHandler для выбора проекта (кнопка)
    select_conv_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex('^🔄 Выбрать проект$'), button_select_project_start)],
        states={
            ENTERING_PROJECT_TO_SELECT: [MessageHandler(filters.TEXT & ~filters.COMMAND, button_select_project_finish)],
        },
        fallbacks=[CommandHandler("cancel", conversation_cancel)],
        name="select_project_button_conversation",
        persistent=False
    )
    application.add_handler(select_conv_handler)
    
    # ConversationHandler для удаления проекта (кнопка)
    delete_button_conv_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex('^🗑️ Удалить проект$'), button_delete_project_start)],
        states={
            ENTERING_PROJECT_TO_DELETE: [MessageHandler(filters.TEXT & ~filters.COMMAND, button_delete_project_confirm)],
            CONFIRMING_DELETE: [MessageHandler(filters.TEXT & ~filters.COMMAND, button_delete_project_finish)],
        },
        fallbacks=[CommandHandler("cancel", conversation_cancel)],
        name="delete_project_button_conversation",
        persistent=False
    )
    application.add_handler(delete_button_conv_handler)
