"""Telegram keyboard builders and regex helpers for menu buttons."""

import re


def get_main_menu_keyboard():
    """Return main menu keyboard."""
    import config
    from telegram import ReplyKeyboardMarkup

    btn = config.MAIN_MENU_BUTTONS
    keyboard = [
        [btn["add"], btn["month"], btn["day"]],
        [btn["incomes"], btn["budget"], btn["settings"]],
        [btn["projects"], btn["analysis"], btn["help"]],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def get_analysis_menu_keyboard():
    """Return analysis submenu keyboard."""
    import config
    from telegram import ReplyKeyboardMarkup

    btn = config.ANALYSIS_MENU_BUTTONS
    keyboard = [
        [btn["stats"], btn["report"]],
        [btn["export"], btn["back"]],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def get_income_menu_keyboard():
    """Return income submenu keyboard."""
    import config
    from telegram import ReplyKeyboardMarkup

    btn = config.INCOME_MENU_BUTTONS
    keyboard = [
        [btn["add"], btn["categories"]],
        [btn["recurring"], btn["back"]],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def get_settings_menu_keyboard():
    """Return settings submenu keyboard."""
    import config
    from telegram import ReplyKeyboardMarkup

    btn = config.SETTINGS_MENU_BUTTONS
    keyboard = [
        [btn["categories"], btn["recurring"]],
        [btn["back"]],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def main_menu_button_regex(key: str) -> str:
    """Match main menu button text exactly."""
    import config

    return "^" + re.escape(config.MAIN_MENU_BUTTONS[key]) + "$"


def category_menu_button_regex(key: str) -> str:
    """Match category menu button text exactly."""
    import config

    return "^" + re.escape(config.CATEGORY_MENU_BUTTONS[key]) + "$"


def project_menu_button_regex(key: str) -> str:
    """Match project menu button text exactly."""
    import config

    return "^" + re.escape(config.PROJECT_MENU_BUTTONS[key]) + "$"


def budget_menu_button_regex(key: str) -> str:
    """Match budget menu button text exactly."""
    import config

    return "^" + re.escape(config.BUDGET_MENU_BUTTONS[key]) + "$"


def analysis_menu_button_regex(key: str) -> str:
    """Match analysis menu button text exactly."""
    import config

    return "^" + re.escape(config.ANALYSIS_MENU_BUTTONS[key]) + "$"


def income_menu_button_regex(key: str) -> str:
    """Match income menu button text exactly."""
    import config

    return "^" + re.escape(config.INCOME_MENU_BUTTONS[key]) + "$"


def settings_menu_button_regex(key: str) -> str:
    """Match settings menu button text exactly."""
    import config

    return "^" + re.escape(config.SETTINGS_MENU_BUTTONS[key]) + "$"
