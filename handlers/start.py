"""
Обработчики команды /start и справки
"""

from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler, filters, MessageHandler
from utils import excel, projects, helpers
from utils.logger import get_logger, log_command, log_event, log_error
import config
from utils import helpers as btn_helpers
from metrics import (
    track_command,
    track_handler_start,
    track_handler_success,
    track_handler_error,
    classify_error_type,
)

logger = get_logger("handlers.start")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Обрабатывает команду /start
    Также обрабатывает приглашения в проекты: /start inv_TOKEN
    """
    track_command("start")
    track_handler_start("start")
    error_type = None
    user_id = update.effective_user.id
    first_name = update.effective_user.first_name
        
    try:
        # Check if there's an invitation token in the command
        if context.args and len(context.args) > 0:
            arg = context.args[0]
            
            # Check if this is an invitation token (starts with inv_)
            if arg.startswith('inv_'):
                # Handle invitation in a separate function
                from handlers.invitations import handle_start_with_invitation
                await handle_start_with_invitation(update, context)
                return
        
        # Normal /start command
        # Создаем директорию для пользователя
        excel.create_user_dir(user_id)
        log_event(logger, "user_dir_created", user_id=user_id)
        
        reply_markup = helpers.get_main_menu_keyboard()
        
        # Инициализируем активный проект из БД
        try:
            active_project = await projects.get_active_project(user_id)
            if active_project:
                context.user_data['active_project_id'] = active_project['project_id']
                log_event(logger, "active_project_loaded", user_id=user_id, 
                         project_id=active_project['project_id'], 
                         project_name=active_project.get('project_name'))
            else:
                context.user_data['active_project_id'] = None
                log_event(logger, "no_active_project", user_id=user_id)
        except Exception as e:
            log_error(logger, e, "load_active_project_error", user_id=user_id)
            context.user_data['active_project_id'] = None

        # Отправляем приветственное сообщение
        message = (
            f"👋 Привет, {first_name}!\n\n"
            f"Я бот для учета и анализа расходов. С моей помощью вы можете:\n"
            f"• Записывать свои расходы по категориям\n"
            f"• Записывать доходы в отдельном разделе\n"
            f"• Получать статистику за месяц\n"
            f"• Анализировать расходы с помощью графиков\n\n"
            f"Чтобы добавить расход, используйте команду:\n"
            f"/add <сумма> <категория> [описание]\n\n"
            f"Например: /add 100 продукты хлеб и молоко\n\n"
            f"Или просто отправьте сообщение в формате:\n"
            f"<сумма> <категория> [описание]\n\n"
            f"Например: 100 продукты хлеб и молоко\n\n"
            f"Для получения справки используйте команду /help"
        )
        
        await update.message.reply_text(message, reply_markup=reply_markup)
        log_event(logger, "start_success", user_id=user_id, status="success")
        
    except Exception as e:
        error_type = classify_error_type(e)
        log_error(logger, e, "start_error", user_id=user_id)
        await update.message.reply_text("❌ Произошла ошибка при запуске бота. Попробуйте позже.")
    finally:
        if error_type:
            track_handler_error("start", error_type)
        else:
            track_handler_success("start")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Обрабатывает команду /help
    """
    track_command("help")
    track_handler_start("help")
    error_type = None
    user_id = update.effective_user.id
    
    log_command(logger, "help", user_id=user_id)
    
    try:
        # Формируем справочное сообщение
        message = (
            "📋 Список доступных команд:\n\n"
            "📁 Управление проектами:\n"
            "• /project_create <название> - создать проект\n"
            "• /project_list - список проектов\n"
            "• /project_select <название или ID> - переключиться на проект\n"
            "• /project_main - переключиться на общие расходы\n"
            "• /project_delete <название или ID> - удалить проект\n"
            "• /project_info - информация о текущем проекте\n\n"
            "👥 Совместная работа:\n"
            "• /project_settings - управление проектом (UI)\n"
            "• /invite [роль] - создать приглашение (владелец)\n"
            "• /members - список участников\n\n"
            "💰 Учет расходов:\n"
            "• /add <сумма> <категория> [описание] - добавить расход\n"
            "• Раздел «💵 Доходы» - добавить доход, управлять категориями и постоянными доходами\n"
            "• Раздел «💵 Доходы» → «🔁 Постоянные» - настроить автодобавление регулярных доходов\n"
            "• Раздел «🔁 Постоянные» - настроить автодобавление регулярных расходов\n"
            "• /month - статистика за текущий месяц\n"
            "• /day - статистика за текущий день\n"
            "• /stats - общая статистика расходов\n"
            "• /category - перечень всех возможных категорий\n"
            "• /category <название> - расходы по категории\n"
            "• /delete_category - удалить пользовательскую категорию\n"
            "• /export - экспорт детальной статистики в Excel\n"
            "• /report - генерация PDF-отчета с графиками\n"
            "• /help - показать эту справку\n\n"
            "📊 Доступные категории расходов:\n"
        )
        
        # Добавляем список категорий
        for category, emoji in config.DEFAULT_CATEGORIES.items():
            message += f"• {emoji} {category}\n"
        
        message += (
            "\n💡 Вы также можете добавлять расходы, просто отправив сообщение в формате:\n"
            "<сумма> <категория> [описание]\n\n"
            "Например: 100 продукты хлеб и молоко"
        )
        
        await update.message.reply_text(message)
        log_event(logger, "help_success", user_id=user_id, status="success")
    except Exception as e:
        error_type = classify_error_type(e)
        log_error(logger, e, "help_error", user_id=user_id)
        await update.message.reply_text("❌ Произошла ошибка при получении справки.")
    finally:
        if error_type:
            track_handler_error("help", error_type)
        else:
            track_handler_success("help")

async def projects_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Отображает меню управления проектами
    """
    track_handler_start("projects_menu")
    error_type = None
    user_id = update.effective_user.id
    
    log_event(logger, "projects_menu_opened", user_id=user_id)
    
    try:
        btn = config.PROJECT_MENU_BUTTONS
        keyboard = [
            [btn["create"], btn["list"]],
            [btn["select"], btn["all_expenses"]],
            [btn["info"], btn["settings"]],
            [btn["delete"], btn["main_menu"]],
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        
        await update.message.reply_text(
            "📁 Меню управления проектами:\n\n"
            "Выберите действие:",
            reply_markup=reply_markup
        )
        log_event(logger, "projects_menu_success", user_id=user_id)
    except Exception as e:
        error_type = classify_error_type(e)
        log_error(logger, e, "projects_menu_error", user_id=user_id)
    finally:
        if error_type:
            track_handler_error("projects_menu", error_type)
        else:
            track_handler_success("projects_menu")

async def main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Возвращает в главное меню
    """
    track_handler_start("main_menu")
    error_type = None
    try:
        reply_markup = helpers.get_main_menu_keyboard()
        await update.message.reply_text(
            "✅ Возвращение в главное меню",
            reply_markup=reply_markup
        )
    except Exception as e:
        error_type = classify_error_type(e)
        log_error(logger, e, "main_menu_error")
        await update.message.reply_text("❌ Не удалось открыть главное меню. Попробуйте позже.")
    finally:
        if error_type:
            track_handler_error("main_menu", error_type)
        else:
            track_handler_success("main_menu")


async def settings_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Отображает подменю настроек.
    """
    track_handler_start("settings_menu")
    error_type = None
    try:
        await update.message.reply_text(
            "⚙️ Настройки\n\nВыберите действие:",
            reply_markup=helpers.get_settings_menu_keyboard()
        )
    except Exception as e:
        error_type = classify_error_type(e)
        log_error(logger, e, "settings_menu_error")
        await update.message.reply_text("❌ Не удалось открыть настройки. Попробуйте позже.")
    finally:
        if error_type:
            track_handler_error("settings_menu", error_type)
        else:
            track_handler_success("settings_menu")

def register_start_handlers(application):
    """
    Регистрирует обработчики команд /start и /help
    """
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    
    # Обработчики для кнопок меню (тексты из config.MAIN_MENU_BUTTONS)
    application.add_handler(MessageHandler(filters.Regex(btn_helpers.main_menu_button_regex("projects")), projects_menu))
    application.add_handler(MessageHandler(filters.Regex(btn_helpers.main_menu_button_regex("settings")), settings_menu))
    application.add_handler(MessageHandler(filters.Regex(btn_helpers.main_menu_button_regex("main_menu")), main_menu))
    application.add_handler(MessageHandler(filters.Regex(btn_helpers.main_menu_button_regex("help")), help_command))
