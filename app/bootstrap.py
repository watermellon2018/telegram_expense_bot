"""Telegram application bootstrap and dependency wiring."""

from telegram.ext import Application

import config
from app.error_handlers import build_error_handler
from app.lifecycle import on_shutdown, on_startup
from handlers import register_all_handlers
from utils.logging_middleware import LoggingHandler


def build_application() -> Application:
    """Build and configure Telegram Application instance."""
    application = (
        Application.builder()
        .token(config.TOKEN)
        .post_init(on_startup)
        .post_stop(on_shutdown)
        .build()
    )

    register_all_handlers(application)
    application.add_handler(LoggingHandler, group=-1)
    application.add_error_handler(build_error_handler())
    return application
