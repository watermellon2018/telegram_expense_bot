"""Обработчик подменю «Доходы»."""

from telegram import Update
from telegram.ext import ContextTypes, MessageHandler, filters

from utils.helpers import get_income_menu_keyboard, main_menu_button_regex, income_menu_button_regex, get_main_menu_keyboard
from utils.logger import get_logger, log_event

logger = get_logger("handlers.income_menu")


async def income_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывает подменю доходов."""
    user_id = update.effective_user.id
    log_event(logger, "income_menu_opened", user_id=user_id)

    await update.message.reply_text(
        "💵 Доходы\n\nВыберите действие:",
        reply_markup=get_income_menu_keyboard(),
    )


async def income_menu_back(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Возврат в главное меню из подменю доходов."""
    await update.message.reply_text("⬅️ Возврат в главное меню", reply_markup=get_main_menu_keyboard())


def register_income_menu_handlers(application):
    """Регистрация обработчиков подменю доходов."""
    application.add_handler(MessageHandler(filters.Regex(main_menu_button_regex("incomes")), income_menu))
    application.add_handler(MessageHandler(filters.Regex(income_menu_button_regex("back")), income_menu_back))
