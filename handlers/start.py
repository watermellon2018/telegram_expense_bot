"""
Обработчики команды /start и справки
"""

from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import CallbackContext, CommandHandler, Filters, MessageHandler
from utils import excel
import config

def start(update: Update, context: CallbackContext) -> None:
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
        ['/category', '/budget', '/help']
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
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
    
    update.message.reply_text(message, reply_markup=reply_markup)

def help_command(update: Update, context: CallbackContext) -> None:
    """
    Обрабатывает команду /help
    """
    # Формируем справочное сообщение
    message = (
        "📋 Список доступных команд:\n\n"
        "• /add <сумма> <категория> [описание] - добавить расход\n"
        "• /month - статистика за текущий месяц\n"
        "• /day - статистика за текущий день\n"
        "• /stats - общая статистика расходов\n"
        "• /budget <сумма> - установить бюджет на месяц\n"
        "• /category <название> - расходы по категории\n"
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
    
    update.message.reply_text(message)

def register_start_handlers(dp):
    """
    Регистрирует обработчики команд /start и /help
    """
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("help", help_command))
