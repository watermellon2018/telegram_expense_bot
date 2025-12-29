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
        await update.message.reply_text(
            "❌ Укажите название проекта.\n"
            "Используйте: /project_create <название>\n"
            "Например: /project_create Отпуск"
        )
        return
    
    project_name = parts[1].strip()
    
    # Создаем проект
    result = await projects.create_project(user_id, project_name)
    
    if result['success']:
        # Автоматически переключаемся на созданный проект
        await projects.set_active_project(user_id, result['project_id'])
        
        # Сохраняем в контексте пользователя
        context.user_data['active_project_id'] = result['project_id']
        
        await update.message.reply_text(
            f"✅ {result['message']}\n"
            f"📁 Проект '{project_name}' активирован\n\n"
            f"Теперь все расходы будут записываться в этот проект."
        )
    else:
        await update.message.reply_text(f"❌ {result['message']}")


async def project_list_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Обрабатывает команду /project_list для отображения списка проектов
    """
    user_id = update.effective_user.id
    
    # Получаем список проектов
    all_projects = await projects.get_all_projects(user_id)
    
    if not all_projects:
        await update.message.reply_text(
            "📋 У вас пока нет проектов.\n\n"
            "Создайте проект командой:\n"
            "/project_create <название>"
        )
        return
    
    # Получаем активный проект
    active_project = await projects.get_active_project(user_id)
    active_project_id = active_project['project_id'] if active_project else None
    
    # Формируем список
    message = "📋 Ваши проекты:\n\n"
    
    for project in all_projects:
        project_id = project['project_id']
        project_name = project['project_name']
        created_date = project['created_date']
        
        # Получаем статистику по проекту
        stats = await projects.get_project_stats(user_id, project_id)
        
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
    
    await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN)


async def project_select_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Обрабатывает команду /project_select для переключения на проект
    """
    user_id = update.effective_user.id
    message_text = update.message.text
    
    # Проверяем, содержит ли команда название или ID проекта
    parts = message_text.split(maxsplit=1)
    
    if len(parts) < 2:
        await update.message.reply_text(
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
        project = await projects.get_project_by_id(user_id, int(project_identifier))
    
    # Если не нашли по ID, ищем по названию
    if project is None:
        project = await projects.get_project_by_name(user_id, project_identifier)
    
    if project is None:
        await update.message.reply_text(
            f"❌ Проект '{project_identifier}' не найден.\n\n"
            f"Посмотрите список проектов: /project_list"
        )
        return
    
    # Переключаемся на проект
    result = await projects.set_active_project(user_id, project['project_id'])
    
    if result['success']:
        # Сохраняем в контексте пользователя
        context.user_data['active_project_id'] = project['project_id']
        
        await update.message.reply_text(
            f"✅ {result['message']}\n\n"
            f"Теперь все расходы будут записываться в проект '{project['project_name']}'."
        )
    else:
        await update.message.reply_text(f"❌ {result['message']}")


async def project_main_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Обрабатывает команду /project_main для переключения на общие расходы
    """
    user_id = update.effective_user.id
    
    # Переключаемся на общие расходы
    result = await projects.set_active_project(user_id, None)
    
    if result['success']:
        # Сбрасываем в контексте пользователя
        context.user_data['active_project_id'] = None
        
        await update.message.reply_text(
            f"✅ {result['message']}\n\n"
            f"Теперь все расходы будут записываться в общие расходы."
        )
    else:
        await update.message.reply_text(f"❌ {result['message']}")


async def project_delete_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Начинает процесс удаления проекта
    """
    user_id = update.effective_user.id
    message_text = update.message.text
    
    # Проверяем, содержит ли команда название или ID проекта
    parts = message_text.split(maxsplit=1)
    
    if len(parts) < 2:
        await update.message.reply_text(
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
        project = await projects.get_project_by_id(user_id, int(project_identifier))
    
    # Если не нашли по ID, ищем по названию
    if project is None:
        project = await projects.get_project_by_name(user_id, project_identifier)
    
    if project is None:
        await update.message.reply_text(
            f"❌ Проект '{project_identifier}' не найден.\n\n"
            f"Посмотрите список проектов: /project_list"
        )
        return ConversationHandler.END
    
    # Сохраняем ID проекта в контексте
    context.user_data['delete_project_id'] = project['project_id']
    context.user_data['delete_project_name'] = project['project_name']
    
    # Получаем статистику по проекту
    stats = await projects.get_project_stats(user_id, project['project_id'])
    
    # Создаем клавиатуру для подтверждения
    keyboard = [['Да, удалить', 'Отмена']]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    
    await update.message.reply_text(
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
            await update.message.reply_text(
                "❌ Ошибка: проект не найден.",
                reply_markup=ReplyKeyboardRemove()
            )
            return ConversationHandler.END
        
        # Удаляем проект
        result = await projects.delete_project(user_id, project_id)
        
        if result['success']:
            # Если удаленный проект был активным, сбрасываем контекст
            if context.user_data.get('active_project_id') == project_id:
                context.user_data['active_project_id'] = None
            
            await update.message.reply_text(
                f"✅ {result['message']}\n\n"
                f"Все данные проекта '{project_name}' удалены.",
                reply_markup=ReplyKeyboardRemove()
            )
        else:
            await update.message.reply_text(
                f"❌ {result['message']}",
                reply_markup=ReplyKeyboardRemove()
            )
    else:
        await update.message.reply_text(
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
    await update.message.reply_text(
        "Удаление проекта отменено.",
        reply_markup=ReplyKeyboardRemove()
    )
    
    # Очищаем данные пользователя
    context.user_data.pop('delete_project_id', None)
    context.user_data.pop('delete_project_name', None)
    
    return ConversationHandler.END


def register_project_handlers(application):
    """
    Регистрирует обработчики команд для работы с проектами
    """
    application.add_handler(CommandHandler("project_create", project_create_command))
    application.add_handler(CommandHandler("project_list", project_list_command))
    application.add_handler(CommandHandler("project_select", project_select_command))
    application.add_handler(CommandHandler("project_main", project_main_command))
    
    # ConversationHandler для удаления проекта
    delete_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("project_delete", project_delete_start)],
        states={
            CONFIRMING_DELETE: [
                MessageHandler(filters.Regex('^(Да, удалить|Отмена)$'), project_delete_confirm),
                MessageHandler(filters.TEXT & ~filters.COMMAND, project_delete_confirm)
            ],
        },
        fallbacks=[CommandHandler("cancel", project_delete_cancel)],
        name="delete_project_conversation",
        persistent=False
    )
    application.add_handler(delete_conv_handler)
