"""
Обработчик кнопки «📊 Отчёт» — генерирует и отправляет PDF-отчёт по финансам.
"""

import os
import logging

from telegram import Update
from telegram.ext import ContextTypes, MessageHandler, filters

from utils.helpers import main_menu_button_regex, get_main_menu_keyboard
from utils.logger import get_logger, log_event, log_error
from utils import report_generator

logger = get_logger("handlers.report")


async def report_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    project_id = context.user_data.get('active_project_id')

    log_event(logger, "report_requested", user_id=user_id, project_id=project_id)

    wait_msg = await update.message.reply_text(
        "⏳ Генерирую отчёт, это может занять несколько секунд…"
    )

    try:
        pdf_path = await report_generator.generate_pdf_report(user_id, project_id)

        if pdf_path is None or not os.path.exists(pdf_path):
            await wait_msg.delete()
            await update.message.reply_text(
                "📭 Нет данных для построения отчёта.\n"
                "Добавьте расходы и повторите попытку.",
                reply_markup=get_main_menu_keyboard(),
            )
            return

        log_event(logger, "report_generated", user_id=user_id,
                  project_id=project_id, path=pdf_path)

        await wait_msg.delete()
        with open(pdf_path, 'rb') as f:
            await update.message.reply_document(
                document=f,
                filename=os.path.basename(pdf_path),
                caption="📊 Ваш финансовый отчёт готов.",
                reply_markup=get_main_menu_keyboard(),
            )

        log_event(logger, "report_sent", user_id=user_id, project_id=project_id)

    except Exception as e:
        log_error(logger, e, "report_error", user_id=user_id, project_id=project_id)
        try:
            await wait_msg.delete()
        except Exception:
            pass
        await update.message.reply_text(
            "❌ Произошла ошибка при генерации отчёта. Попробуйте позже.",
            reply_markup=get_main_menu_keyboard(),
        )


def register_report_handlers(application):
    application.add_handler(
        MessageHandler(filters.Regex(main_menu_button_regex("report")), report_command)
    )
