"""
Обработчик подменю «Анализ».
Открывает подменю с кнопками: Статистика, Отчёт, Экспорт.
"""

from telegram import Update
from telegram.ext import ContextTypes, MessageHandler, filters

from utils.helpers import get_analysis_menu_keyboard, main_menu_button_regex
from utils.logger import get_logger, log_event

logger = get_logger("handlers.analysis")


async def analysis_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывает подменю «Анализ»."""
    user_id = update.effective_user.id
    log_event(logger, "analysis_menu_opened", user_id=user_id)

    await update.message.reply_text(
        "🔍 Анализ финансов\n\nВыберите действие:",
        reply_markup=get_analysis_menu_keyboard(),
    )


def register_analysis_handlers(application) -> None:
    application.add_handler(
        MessageHandler(
            filters.Regex(main_menu_button_regex("analysis")),
            analysis_command,
        )
    )
