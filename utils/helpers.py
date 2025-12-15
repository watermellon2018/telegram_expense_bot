"""
Вспомогательные функции для Telegram-бота анализа расходов
"""

import re
import datetime
from utils import excel

def parse_add_command(text):
    """
    Парсит команду добавления расхода
    Форматы:
    - /add 100 продукты
    - /add 100 продукты комментарий
    - 100 продукты
    - 100 продукты комментарий
    
    Возвращает словарь с полями amount, category, description или None, если парсинг не удался
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
    
    month_name = datetime.date(year, month, 1).strftime('%B')
    
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
        emoji = DEFAULT_CATEGORIES.get(category, "")
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
    emoji = DEFAULT_CATEGORIES.get(category.lower(), "")
    
    report = f"📊 Статистика расходов по категории {emoji} {category} за {year} год:\n\n"
    report += f"💰 Общая сумма: {category_data['total']:.2f}\n"
    report += f"🧾 Количество транзакций: {category_data['count']}\n\n"
    
    report += "📅 Расходы по месяцам:\n"
    
    # Выводим расходы по месяцам
    for month in range(1, 13):
        month_name = datetime.date(year, month, 1).strftime('%B')
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

def format_budget_status(user_id, month=None, year=None):
    """
    Форматирует статус бюджета на месяц
    """
    if month is None:
        month = datetime.datetime.now().month
    if year is None:
        year = datetime.datetime.now().year

    # Теперь бюджет храним в Postgres.
    # Используем ту же семантику: если строки нет или budget == 0 -> "не установлен".
    async def _do():
        from utils import db

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
        return row

    try:
        row = excel.db.run_async(_do())
    except Exception as e:
        print(f"Ошибка при получении статуса бюджета из БД: {e}")
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
    
    if expenses['status'] == False:
        return expenses['note']
        
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
        emoji = DEFAULT_CATEGORIES.get(category, "")
        percentage = (amount / expenses['total']) * 100
        report += f"{emoji} {category.title()}: {amount:.2f} ({percentage:.1f}%)\n"
    
    return report
