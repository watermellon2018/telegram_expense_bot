"""
Инициализация обработчиков команд для Telegram-бота
"""

from handlers.start import register_start_handlers
from handlers.expense import register_expense_handlers
from handlers.stats import register_stats_handlers
from handlers.export import register_export_handlers
from handlers.project import register_project_handlers
from handlers.category import register_category_handlers

def register_all_handlers(application):
    """
    Регистрирует все обработчики команд
    """
    register_project_handlers(application)
    register_start_handlers(application)

    # Важный порядок! Экспорт и другие кнопки меню — до expense.text_handler (который ловит любой текст)
    register_export_handlers(application)
    register_stats_handlers(application)
    register_category_handlers(application)
    register_expense_handlers(application)
