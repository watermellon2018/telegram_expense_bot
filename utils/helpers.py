"""Backward-compatible facade for helper functions.

The original `utils.helpers` mixed parsing, formatting, menu UI, conversation helpers
and runtime context operations. The implementation has been split into dedicated modules,
while this file preserves the old import path for existing handlers and tests.
"""

from utils.context import get_active_project_id
from utils.conversation import cancel_conversation
from utils.formatting import (
    add_project_context_to_report,
    format_budget_status,
    format_category_expenses,
    format_day_expenses,
    format_month_expenses,
    get_month_name,
)
from utils.menu import (
    analysis_menu_button_regex,
    budget_menu_button_regex,
    category_menu_button_regex,
    get_analysis_menu_keyboard,
    get_income_menu_keyboard,
    get_main_menu_keyboard,
    get_settings_menu_keyboard,
    income_menu_button_regex,
    main_menu_button_regex,
    project_menu_button_regex,
    settings_menu_button_regex,
)
from utils.parsing import parse_add_command

__all__ = [
    "parse_add_command",
    "format_month_expenses",
    "format_category_expenses",
    "get_month_name",
    "format_budget_status",
    "format_day_expenses",
    "cancel_conversation",
    "add_project_context_to_report",
    "get_main_menu_keyboard",
    "get_analysis_menu_keyboard",
    "get_income_menu_keyboard",
    "get_settings_menu_keyboard",
    "main_menu_button_regex",
    "category_menu_button_regex",
    "project_menu_button_regex",
    "budget_menu_button_regex",
    "analysis_menu_button_regex",
    "income_menu_button_regex",
    "settings_menu_button_regex",
    "get_active_project_id",
]
