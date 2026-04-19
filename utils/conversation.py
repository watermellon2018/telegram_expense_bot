"""Shared conversation flow helpers."""

from telegram import Update, ReplyKeyboardRemove
from telegram.ext import ContextTypes, ConversationHandler

from utils.menu import get_main_menu_keyboard


async def cancel_conversation(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    message: str = "Операция отменена.",
    clear_data: bool = False,
    restore_keyboard: bool = True,
) -> int:
    """
    Universal ConversationHandler cancellation helper.
    """
    reply_markup = get_main_menu_keyboard() if restore_keyboard else ReplyKeyboardRemove()
    await update.message.reply_text(message, reply_markup=reply_markup)

    if clear_data:
        context.user_data.clear()

    return ConversationHandler.END
