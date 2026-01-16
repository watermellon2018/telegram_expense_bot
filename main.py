import logging
import os
import pytz
import apscheduler.util

# 1. СТРОГИЙ ПАТЧ ТАЙМЗОНЫ (должен быть в самом верху)
def patched_astimezone(obj):
    if obj is None: return pytz.UTC
    if hasattr(obj, 'localize'): return obj
    return pytz.UTC

apscheduler.util.astimezone = patched_astimezone
apscheduler.util.get_localzone = lambda: pytz.UTC

from telegram.ext import Application
import config
from handlers import register_all_handlers
from utils.db import init_pool, close_pool

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Функция, которая выполнится ПЕРЕД стартом бота
async def on_startup(application: Application):
    os.makedirs(config.DATA_DIR, exist_ok=True)
    await init_pool()
    logger.info("Пул соединений с БД инициализирован через post_init")

# Функция, которая выполнится ПРИ ОСТАНОВКЕ бота
async def on_shutdown(application: Application):
    await close_pool()
    logger.info("Пул соединений закрыт через post_stop")

def main():
    """Главная точка входа (НЕ асинхронная)"""

    # Собираем приложение
    application = (
        Application.builder()
        .token(config.TOKEN)
        .post_init(on_startup)  # Регистрируем запуск БД
        .post_stop(on_shutdown) # Регистрируем закрытие БД
        .build()
    )

    # Регистрация обработчиков
    register_all_handlers(application)

    logger.info("Инициализация системы завершена. Запуск polling...")

    # run_polling САМ создаст и закроет event loop корректно
    application.run_polling(drop_pending_updates=True)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Бот остановлен пользователем")
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}", exc_info=True)