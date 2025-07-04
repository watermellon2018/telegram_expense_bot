"""
Конфигурационный файл для Telegram-бота анализа расходов
"""

import os
from dotenv import load_dotenv

# Загружаем переменные окружения из .env файла
load_dotenv()

# Токен Telegram-бота (заменить на реальный токен при запуске)
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "YOUR_TELEGRAM_BOT_TOKEN")


# Настройки для хранения данных
DATA_DIR = "data/users"

# Доступные категории расходов по умолчанию
DEFAULT_CATEGORIES = {
    "продукты": "🍎",
    "транспорт": "🚌",
    "развлечения": "🎭",
    "рестораны": "🍽️",
    "здоровье": "💊",
    "одежда": "👕",
    "жилье": "🏠",
    "связь": "📱",
    "образование": "📚",
    "спорт": "🏋️",
    "дом": "🏡",
    "инвестиции": "💹",
    "маркетплейсы": "🛒",
    "красота": "💅",
    "прочее": "📦"
}

# Настройки для визуализации
COLORS = {
    "продукты": "#4CAF50",
    "транспорт": "#2196F3",
    "развлечения": "#9C27B0",
    "рестораны": "#FF9800",
    "здоровье": "#F44336",
    "одежда": "#3F51B5",
    "жилье": "#795548",
    "связь": "#00BCD4",
    "образование": "#607D8B",
    "спорт": "#FF5722",
    "дом": "#8BC34A",
    "инвестиции": "#FF9800",
    "маркетплейсы": "#00BCD4",
    "красота": "#FF69B4",
    "прочее": "#9E9E9E"
}

MONTH_NAMES = {
    'январь': 1, 'янв': 1,
    'февраль': 2, 'фев': 2,
    'март': 3, 'мар': 3,
    'апрель': 4, 'апр': 4,
    'май': 5,
    'июнь': 6, 'июн': 6,
    'июль': 7, 'июл': 7,
    'август': 8, 'авг': 8,
    'сентябрь': 9, 'сен': 9, 'сент': 9,
    'октябрь': 10, 'окт': 10,
    'ноябрь': 11, 'ноя': 11, 'нояб': 11,
    'декабрь': 12, 'дек': 12
}


# Формат даты для отображения
DATE_FORMAT = "%d.%m.%Y"

# Формат времени для отображения
TIME_FORMAT = "%H:%M:%S"

# Максимальное количество категорий для отображения на графиках
MAX_CATEGORIES_ON_CHART = 8
