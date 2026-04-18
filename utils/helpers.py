"""
Вспомогательные функции для Telegram-бота анализа расходов
"""

import re
import datetime
import logging
from utils import excel
from telegram import Update, ReplyKeyboardRemove
from telegram.ext import ContextTypes, ConversationHandler

logger = logging.getLogger(__name__)

def parse_add_command(text):
    """
    Парсит команду добавления расхода
    """
    # Удаляем команду /add, если она есть
    if text.startswith('/add '):
        text = text[5:].strip()
    
    # Пытаемся распарсить сумму и категорию
    pattern = r'^(\d+(?:\.\d+)?)\s+(\w+)(?:\s+(.+))?$'
    match = re.match(pattern, text)
    
    if match:
        amount = float(match.group(1))
        category = match.group(2).lower()
        description = match.group(3) if match.group(3) else ""
        
        return {
            'amount': amount,
            'category': category,
            'description': description
        }
    
    return None

def format_month_expenses(expenses, month=None, year=None):
    """
    Форматирует статистику расходов за месяц в текстовый отчет
    """
    if month is None:
        month = datetime.datetime.now().month
    if year is None:
        year = datetime.datetime.now().year
    
    month_name = get_month_name(month)
    
    if not expenses or expenses['total'] == 0:
        return f"В {month_name} {year} года расходов не было."
    
    # Формируем отчет
    report = f"📊 Статистика расходов за {month_name} {year} года:\n\n"
    report += f"💰 Общая сумма: {expenses['total']:.2f}\n"
    report += f"🧾 Количество транзакций: {expenses['count']}\n\n"
    
    report += "📋 Расходы по категориям:\n"
    
    # Сортируем категории по убыванию сумм
    sorted_categories = sorted(
        expenses['by_category'].items(), 
        key=lambda x: x[1], 
        reverse=True
    )
    
    for category, amount in sorted_categories:
        from config import DEFAULT_CATEGORIES
        emoji = DEFAULT_CATEGORIES.get(category, "📦")  # 📦 default for custom categories
        report += f"{emoji} {category.title()}: {amount:.2f}\n"
    
    return report

def format_category_expenses(category_data, category, year=None):
    """
    Форматирует статистику расходов по категории в текстовый отчет
    """
    if year is None:
        year = datetime.datetime.now().year
    
    if not category_data or category_data['total'] == 0:
        return f"В {year} году расходов по категории '{category}' не было."
    
    # Формируем отчет
    from config import DEFAULT_CATEGORIES
    emoji = DEFAULT_CATEGORIES.get(category.lower(), "📦")  # 📦 default for custom categories
    
    report = f"📊 Статистика расходов по категории {emoji} {category} за {year} год:\n\n"
    report += f"💰 Общая сумма: {category_data['total']:.2f}\n"
    report += f"🧾 Количество транзакций: {category_data['count']}\n\n"
    
    report += "📅 Расходы по месяцам:\n"
    
    # Выводим расходы по месяцам
    for month in range(1, 13):
        month_name = get_month_name(month)
        amount = category_data['by_month'].get(month, 0)
        report += f"{month_name}: {amount:.2f}\n"
    
    return report

def get_month_name(month):
    """
    Возвращает название месяца по его номеру
    """
    months = [
        "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
        "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"
    ]
    return months[month - 1]

async def format_budget_status(user_id, month=None, year=None):
    """
    Budget functionality disabled. Returns message.
    """
    if month is None:
        month = datetime.datetime.now().month
    if year is None:
        year = datetime.datetime.now().year
    
    return f"📊 Функция бюджета отключена."
    
    # OLD CODE (disabled):
    if False:
        from utils import db

        try:
            row = await db.fetchrow(
                """
                SELECT budget, actual
                FROM budget
                WHERE user_id = $1
                  AND project_id IS NULL
                  AND month = $2
                """,
                str(user_id),
                month,
            )
        except Exception as e:
            logger.error(f"Ошибка при получении статуса бюджета из БД: {e}")
            row = None

        if not row or float(row["budget"]) == 0:
            return f"Бюджет на {get_month_name(month)} {year} года не установлен."

    budget = float(row["budget"])
    actual = float(row["actual"])
    
    # Рассчитываем процент использования бюджета
    if budget > 0:
        percentage = (actual / budget) * 100
    else:
        percentage = 0
    
    # Формируем отчет
    report = f"📊 Статус бюджета на {get_month_name(month)} {year} года:\n\n"
    report += f"💰 Установленный бюджет: {budget:.2f}\n"
    report += f"💸 Фактические расходы: {actual:.2f}\n"
    
    if actual <= budget:
        remaining = budget - actual
        report += f"✅ Остаток: {remaining:.2f} ({100 - percentage:.1f}%)\n"
    else:
        overspent = actual - budget
        report += f"❌ Перерасход: {overspent:.2f} ({percentage - 100:.1f}%)\n"
    
    return report

def format_day_expenses(expenses, date=None):
    """
    Форматирует статистику расходов за день в текстовый отчет
    """
    if date is None:
        date = datetime.datetime.now().strftime('%Y-%m-%d')
    
    if not expenses or expenses['total'] == 0:
        return f"Расходов за {date} не было."
    
    # Форматируем отчет
    report = f"📊 Статистика расходов за {date}:\n\n"
    report += f"💰 Общая сумма: {expenses['total']:.2f}\n"
    report += f"🧾 Количество транзакций: {expenses['count']}\n\n"
    
    report += "📋 Расходы по категориям:\n"
    
    # Сортируем категории по убыванию сумм
    sorted_categories = sorted(
        expenses['by_category'].items(), 
        key=lambda x: x[1], 
        reverse=True
    )
    
    for category, amount in sorted_categories:
        from config import DEFAULT_CATEGORIES
        emoji = DEFAULT_CATEGORIES.get(category, "📦")  # 📦 default for custom categories
        percentage = (amount / expenses['total']) * 100
        report += f"{emoji} {category.title()}: {amount:.2f} ({percentage:.1f}%)\n"
    
    return report


async def cancel_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE, message: str = "Операция отменена.", clear_data: bool = False, restore_keyboard: bool = True) -> int:
    """
    Универсальная функция для отмены ConversationHandler.
    
    Args:
        update: Telegram Update объект
        context: Контекст бота
        message: Сообщение пользователю (по умолчанию "Операция отменена.")
        clear_data: Очистить ли context.user_data (по умолчанию False)
        restore_keyboard: Восстановить ли главное меню после отмены (по умолчанию True)
    
    Returns:
        ConversationHandler.END
    """
    if restore_keyboard:
        reply_markup = get_main_menu_keyboard()
    else:
        reply_markup = ReplyKeyboardRemove()
    
    await update.message.reply_text(message, reply_markup=reply_markup)
    
    if clear_data:
        context.user_data.clear()
    
    return ConversationHandler.END


async def add_project_context_to_report(report: str, user_id: int, project_id: int = None) -> str:
    """
    Добавляет информацию о текущем проекте в начало отчета.
    
    Args:
        report: Исходный текст отчета
        user_id: ID пользователя
        project_id: ID активного проекта (None для общих расходов)
    
    Returns:
        Отчет с добавленной информацией о проекте
    """
    if project_id is not None:
        from utils import projects
        project = await projects.get_project_by_id(user_id, project_id)
        if project:
            return f"📁 Проект: {project['project_name']}\n\n{report}"
    
    return f"📊 Общие расходы\n\n{report}"


def get_main_menu_keyboard():
    """
    Возвращает клавиатуру главного меню.
    Тексты кнопок берутся из config.MAIN_MENU_BUTTONS.
    """
    import config
    from telegram import ReplyKeyboardMarkup
    btn = config.MAIN_MENU_BUTTONS
    keyboard = [
        [btn["add"],     btn["month"],       btn["day"]      ],
        [btn["incomes"], btn["budget"],      btn["settings"] ],
        [btn["projects"], btn["analysis"], btn["help"] ],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def get_analysis_menu_keyboard():
    """Возвращает клавиатуру подменю «Анализ»."""
    import config
    from telegram import ReplyKeyboardMarkup
    btn = config.ANALYSIS_MENU_BUTTONS
    keyboard = [
        [btn["stats"],  btn["report"]],
        [btn["export"], btn["back"]],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def get_income_menu_keyboard():
    """Возвращает клавиатуру подменю «Доходы»."""
    import config
    from telegram import ReplyKeyboardMarkup
    btn = config.INCOME_MENU_BUTTONS
    keyboard = [
        [btn["add"], btn["categories"]],
        [btn["recurring"], btn["back"]],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def get_settings_menu_keyboard():
    """Возвращает клавиатуру подменю «Настройки»."""
    import config
    from telegram import ReplyKeyboardMarkup
    btn = config.SETTINGS_MENU_BUTTONS
    keyboard = [
        [btn["categories"], btn["recurring"]],
        [btn["back"]],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def main_menu_button_regex(key: str) -> str:
    """Точное совпадение с кнопкой главного меню (для filters.Regex)."""
    import config
    return "^" + re.escape(config.MAIN_MENU_BUTTONS[key]) + "$"


def category_menu_button_regex(key: str) -> str:
    """Точное совпадение с кнопкой меню категорий (для filters.Regex)."""
    import config
    return "^" + re.escape(config.CATEGORY_MENU_BUTTONS[key]) + "$"


def project_menu_button_regex(key: str) -> str:
    """Точное совпадение с кнопкой меню проектов (для filters.Regex)."""
    import config
    return "^" + re.escape(config.PROJECT_MENU_BUTTONS[key]) + "$"


def budget_menu_button_regex(key: str) -> str:
    """Точное совпадение с кнопкой меню бюджета (для filters.Regex)."""
    import config
    return "^" + re.escape(config.BUDGET_MENU_BUTTONS[key]) + "$"


def analysis_menu_button_regex(key: str) -> str:
    """Точное совпадение с кнопкой подменю «Анализ» (для filters.Regex)."""
    import config
    return "^" + re.escape(config.ANALYSIS_MENU_BUTTONS[key]) + "$"


def income_menu_button_regex(key: str) -> str:
    """Точное совпадение с кнопкой подменю «Доходы» (для filters.Regex)."""
    import config
    return "^" + re.escape(config.INCOME_MENU_BUTTONS[key]) + "$"


def settings_menu_button_regex(key: str) -> str:
    """Точное совпадение с кнопкой подменю «Настройки» (для filters.Regex)."""
    import config
    return "^" + re.escape(config.SETTINGS_MENU_BUTTONS[key]) + "$"


async def get_active_project_id(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Get active project ID for user.
    Loads from database if not in context memory.
    
    Args:
        user_id: User ID
        context: Telegram context
    
    Returns:
        project_id or None
    """
    from utils import projects
    from utils.logger import get_logger, log_event, log_error
    
    logger = get_logger("utils.helpers")
    
    # Check if already in context
    if 'active_project_id' in context.user_data:
        return context.user_data['active_project_id']
    
    # Load from database
    try:
        active_project = await projects.get_active_project(user_id)
        if active_project:
            project_id = active_project['project_id']
            context.user_data['active_project_id'] = project_id
            log_event(logger, "active_project_loaded_from_db", 
                     user_id=user_id, project_id=project_id)
            return project_id
        else:
            context.user_data['active_project_id'] = None
            return None
    except Exception as e:
        log_error(logger, e, "load_active_project_error", user_id=user_id)
        context.user_data['active_project_id'] = None
        return None
