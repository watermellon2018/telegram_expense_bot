"""Centralized registration of Telegram handlers."""

from handlers.analysis import register_analysis_handlers
from handlers.budget import register_budget_handlers
from handlers.category import register_category_handlers
from handlers.expense import register_expense_handlers
from handlers.export import register_export_handlers
from handlers.income import register_income_handlers
from handlers.income_category import register_income_category_handlers
from handlers.income_menu import register_income_menu_handlers
from handlers.invitations import register_invitation_handlers
from handlers.project import register_project_handlers
from handlers.project_management import register_project_management_handlers
from handlers.recurring import register_recurring_handlers
from handlers.recurring_income import register_recurring_income_handlers
from handlers.report import register_report_handlers
from handlers.start import register_start_handlers
from handlers.stats import register_stats_handlers


def register_all_handlers(application):
    """Register all command and conversation handlers in strict order."""
    register_project_handlers(application)
    register_invitation_handlers(application)
    register_project_management_handlers(application)
    register_start_handlers(application)

    # Menu handlers must be above generic expense text handler.
    register_analysis_handlers(application)
    register_export_handlers(application)
    register_report_handlers(application)
    register_stats_handlers(application)
    register_income_menu_handlers(application)
    register_income_category_handlers(application)
    register_recurring_income_handlers(application)
    register_income_handlers(application)
    register_category_handlers(application)
    register_budget_handlers(application)
    register_recurring_handlers(application)
    register_expense_handlers(application)
