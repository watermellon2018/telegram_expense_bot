"""
Главный файл Telegram-бота для анализа расходов
"""

import os
import logging
from telegram.ext import Updater, CommandHandler
import config
from handlers import register_all_handlers

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


def main():
    """
    Основная функция запуска бота
    """
    # Создаем директорию для данных, если она не существует
    if not os.path.exists(config.DATA_DIR):
        os.makedirs(config.DATA_DIR)
    
    # Создаем Updater и передаем ему токен бота
    updater = Updater(config.TOKEN)

    # Получаем диспетчер для регистрации обработчиков
    dp = updater.dispatcher
    
    # Регистрируем все обработчики команд
    register_all_handlers(dp)


    # Запускаем бота
    updater.start_polling()
    logger.info("Бот запущен")
    
    # Останавливаем бота при нажатии Ctrl+C
    updater.idle()

if __name__ == '__main__':
    main()
