"""
Обработчики команды /start и справки
"""

from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler, filters, MessageHandler
from utils import excel
import config

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Обрабатывает команду /start
    """
    user_id = update.effective_user.id
    first_name = update.effective_user.first_name
    
    # Создаем директорию для пользователя
    excel.create_user_dir(user_id)
    
    # Создаем клавиатуру с основными командами
    keyboard = [
        ['/add', '/month', '/day', '/stats'],
        ['/category', '/budget', '/export', '/export_stats'],
        ['📁 Проекты', '/help']
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
    # Инициализируем активный проект из БД
    from utils import projects
    active_project = await projects.get_active_project(user_id)
    if active_project:
        context.user_data['active_project_id'] = active_project['project_id']
    else:
        context.user_data['active_project_id'] = None

    # Отправляем приветственное сообщение
    message = (
        f"👋 Привет, {first_name}!\n\n"
        f"Я бот для учета и анализа расходов. С моей помощью вы можете:\n"
        f"• Записывать свои расходы по категориям\n"
        f"• Получать статистику за месяц\n"
        f"• Анализировать расходы с помощью графиков\n"
        f"• Устанавливать бюджет и следить за его исполнением\n\n"
        f"Чтобы добавить расход, используйте команду:\n"
        f"/add <сумма> <категория> [описание]\n\n"
        f"Например: /add 100 продукты хлеб и молоко\n\n"
        f"Или просто отправьте сообщение в формате:\n"
        f"<сумма> <категория> [описание]\n\n"
        f"Например: 100 продукты хлеб и молоко\n\n"
        f"Для получения справки используйте команду /help"
    )
    
    await update.message.reply_text(message, reply_markup=reply_markup)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Обрабатывает команду /help
    """
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
        "💰 Учет расходов:\n"
        "• /add <сумма> <категория> [описание] - добавить расход\n"
        "• /month - статистика за текущий месяц\n"
        "• /day - статистика за текущий день\n"
        "• /stats - общая статистика расходов\n"
        "• /budget <сумма> - установить бюджет на месяц\n"
        "• /category - перечень всех возможных категорий\n"
        "• /category <название> - расходы по категории\n"
        "• /export - экспорт всех расходов в Excel\n"
        "• /export_stats - экспорт детальной статистики\n"
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

async def projects_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Отображает меню управления проектами
    """
    # Создаем клавиатуру с функциями проектов
    keyboard = [
        ['🆕 Создать проект', '📋 Список проектов'],
        ['🔄 Выбрать проект', '📊 Общие расходы'],
        ['ℹ️ Инфо о проекте', '🗑️ Удалить проект'],
        ['⬅️ Главное меню']
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
    await update.message.reply_text(
        "📁 Меню управления проектами:\n\n"
        "Выберите действие:",
        reply_markup=reply_markup
    )

async def main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Возвращает в главное меню
    """
    keyboard = [
        ['/add', '/month', '/day', '/stats'],
        ['/category', '/budget', '/export', '/export_stats'],
        ['📁 Проекты', '/help']
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
    await update.message.reply_text(
        "✅ Возвращение в главное меню",
        reply_markup=reply_markup
    )

def register_start_handlers(application):
    """
    Регистрирует обработчики команд /start и /help
    """
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    
    # Обработчики для кнопок меню
    application.add_handler(MessageHandler(filters.Regex('^📁 Проекты$'), projects_menu))
    application.add_handler(MessageHandler(filters.Regex('^⬅️ Главное меню$'), main_menu))
