"""
Инициализация обработчиков команд для Telegram-бота
"""

from handlers.start import register_start_handlers
from handlers.expense import register_expense_handlers
from handlers.stats import register_stats_handlers
from handlers.reminder import register_reminder_handlers

def register_all_handlers(dp):
    """
    Регистрирует все обработчики команд
    """
    register_start_handlers(dp)

    # Важный порядок! В противном случае будет проблема с перехваткой сообщений
    # Так как оба метода отслеживают ввод
    register_stats_handlers(dp)
    register_expense_handlers(dp)

    register_reminder_handlers(dp)
