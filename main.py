"""
Главный файл Telegram-бота для анализа расходов
(используется python-telegram-bot v22.5)
"""

import asyncio
import logging
import os

# Патчим get_localzone ДО импорта Application, чтобы APScheduler использовал pytz timezone
import pytz

# Monkey-patch get_localzone чтобы возвращать pytz timezone
# Это нужно для APScheduler, который требует pytz timezone на Windows
def _patched_get_localzone():
    return pytz.UTC

# Патчим tzlocal.get_localzone
try:
    import tzlocal
    tzlocal.get_localzone = _patched_get_localzone
except ImportError:
    pass

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
        # Создаём JobQueue вручную с явным указанием pytz timezone
        # Это нужно, потому что JobQueue создаётся автоматически при Application.builder()
        # и пытается использовать системный timezone, который несовместим с pytz на Windows
        job_queue = JobQueue()
        # Настраиваем timezone сразу после создания
        job_queue.scheduler.configure(timezone=pytz.UTC)
        
        # Создаём приложение с предварительно настроенным JobQueue
        application = (
            Application.builder()
            .token(config.TOKEN)
            .job_queue(job_queue)
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