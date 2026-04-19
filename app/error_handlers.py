"""Global Telegram error handling."""

from telegram import Update
from telegram.ext import ContextTypes

from metrics import classify_error_type, track_error_only
from utils.logger import get_logger, log_error


def build_error_handler():
    """Builds application-level Telegram error handler."""
    error_logger = get_logger("telegram.errors")

    async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        user_id = None
        update_id = None

        if isinstance(update, Update):
            update_id = update.update_id
            if update.effective_user:
                user_id = update.effective_user.id

        log_error(
            error_logger,
            context.error,
            "telegram_error",
            user_id=user_id,
            update_id=update_id,
        )
        track_error_only("global_error_handler", classify_error_type(context.error))

    return error_handler
