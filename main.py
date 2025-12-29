"""
Главный файл Telegram-бота для анализа расходов
(используется python-telegram-bot v22.5)
"""

import asyncio
import logging
import os

# APScheduler и часовые пояса: в новых версиях рекомендуется использовать стандартный ZoneInfo или оставить по умолчанию.
# Если возникают проблемы с pytz, лучше использовать UTC напрямую через datetime.timezone.utc.
import datetime

from telegram.ext import Application, JobQueue

import config
from handlers import register_all_handlers
from utils.db import init_pool, close_pool

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


async def error_handler(update: object, context):
    logger.error("Необработанная ошибка:", exc_info=context.error)


async def main():
    os.makedirs(config.DATA_DIR, exist_ok=True)

    await init_pool()
    logger.info("Пул соединений с БД инициализирован")

    try:
        # Создаём приложение. JobQueue будет создан автоматически.
        # Если возникнут проблемы с таймзонами, APScheduler можно настроить через job_queue.scheduler.configure
        application = (
            Application.builder()
            .token(config.TOKEN)
            .build()
        )

        register_all_handlers(application)
        application.add_error_handler(error_handler)

        logger.info("Бот запущен и готов к работе")

        await application.run_polling(drop_pending_updates=True)

    finally:
        await close_pool()
        logger.info("Пул соединений закрыт")


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Бот остановлен пользователем")
    except Exception as e:
        logger.error(f"Критическая ошибка при запуске: {e}", exc_info=True)