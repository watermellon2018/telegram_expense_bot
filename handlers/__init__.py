"""
Инициализация обработчиков команд для Telegram-бота
"""

from handlers.start import register_start_handlers
from handlers.expense import register_expense_handlers
from handlers.stats import register_stats_handlers
from handlers.export import register_export_handlers
from handlers.report import register_report_handlers
from handlers.project import register_project_handlers
from handlers.category import register_category_handlers
from handlers.invitations import register_invitation_handlers
from handlers.project_management import register_project_management_handlers
from handlers.budget import register_budget_handlers
from handlers.analysis import register_analysis_handlers
from handlers.recurring import register_recurring_handlers
from handlers.income_menu import register_income_menu_handlers
from handlers.income import register_income_handlers
from handlers.income_category import register_income_category_handlers
from handlers.recurring_income import register_recurring_income_handlers

def register_all_handlers(application):
    """
    Регистрирует все обработчики команд
    """
    register_project_handlers(application)
    register_invitation_handlers(application)  # Register before start handlers
    register_project_management_handlers(application)  # Register management UI
    register_start_handlers(application)

    # Важный порядок! Кнопки меню — до expense.text_handler (который ловит любой текст)
    register_analysis_handlers(application)    # Подменю «Анализ» — до дочерних обработчиков
    register_export_handlers(application)
    register_report_handlers(application)      # Отчёт — до expense
    register_stats_handlers(application)
    register_income_menu_handlers(application)  # Подменю «Доходы»
    register_income_category_handlers(application)
    register_recurring_income_handlers(application)
    register_income_handlers(application)
    register_category_handlers(application)
    register_budget_handlers(application)      # Бюджет — до expense (expense ловит любой текст)
    register_recurring_handlers(application)   # Постоянные расходы — до expense
    register_expense_handlers(application)     # ПОСЛЕДНИМ: ловит любой текст
