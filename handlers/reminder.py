"""
Модуль для реализации альтернативных решений автоматической отправки статистики
"""

import datetime
from telegram import Update, ParseMode
from telegram.ext import CallbackContext, CommandHandler
from utils import excel, helpers, visualization
import os

def setup_monthly_reminder(update: Update, context: CallbackContext) -> None:
    """
    Настраивает напоминание о необходимости запросить статистику в конце месяца
    """
    user_id = update.effective_user.id
    
    # Объясняем пользователю ограничения и предлагаем альтернативы
    message = (
        "⚠️ Информация о функции автоматической отправки статистики\n\n"
        "К сожалению, функция автоматической отправки статистики в конце месяца "
        "временно недоступна из-за технических ограничений.\n\n"
        "Вместо этого вы можете:\n\n"
        "1️⃣ Использовать команду /month в любое время для получения статистики за текущий месяц\n\n"
        "2️⃣ Использовать команду /stats для получения полного анализа с графиками\n\n"
        "3️⃣ Настроить напоминание в своем календаре на последний день месяца\n\n"
        "4️⃣ Использовать команду /remind, чтобы получить инструкции по настройке напоминаний\n\n"
        "Мы работаем над добавлением автоматической отправки статистики в будущих обновлениях."
    )
    
    update.message.reply_text(message)

def remind_command(update: Update, context: CallbackContext) -> None:
    """
    Отправляет инструкции по настройке напоминаний
    """
    # Формируем инструкцию
    message = (
        "📅 Как настроить напоминания о статистике расходов\n\n"
        "Поскольку автоматическая отправка статистики временно недоступна, "
        "вы можете настроить напоминания следующими способами:\n\n"
        
        "1️⃣ Использование календаря в телефоне:\n"
        "• Создайте ежемесячное событие на последний день месяца\n"
        "• Добавьте напоминание с текстом 'Запросить статистику расходов: /stats'\n"
        "• Настройте уведомление, чтобы не забыть запросить статистику\n\n"
        
        "2️⃣ Использование других приложений-напоминалок:\n"
        "• Настройте ежемесячное напоминание\n"
        "• Добавьте в текст напоминания команды /month или /stats\n\n"
        
        "3️⃣ Ручной запрос статистики:\n"
        "• В любой момент используйте команду /month для получения статистики за текущий месяц\n"
        "• Используйте команду /stats для получения полного анализа с графиками\n\n"
        
        "Мы работаем над добавлением автоматической отправки статистики в будущих обновлениях."
    )
    
    update.message.reply_text(message)

def end_of_month_stats(update: Update, context: CallbackContext) -> None:
    """
    Отправляет полную статистику за месяц по запросу
    Имитирует функцию, которая должна была бы выполняться автоматически в конце месяца
    """
    user_id = update.effective_user.id
    
    # Получаем текущий месяц и год
    now = datetime.datetime.now()
    month = now.month
    year = now.year
    month_name = helpers.get_month_name(month)
    
    # Получаем статистику расходов
    expenses = excel.get_month_expenses(user_id, month, year)
    
    # Формируем отчет
    report = (
        f"📊 Итоговая статистика расходов за {month_name} {year} года\n\n"
    )
    
    if not expenses or expenses['total'] == 0:
        report += f"В {month_name} {year} года расходов не было."
        update.message.reply_text(report)
        return
    
    # Добавляем общую статистику
    report += f"💰 Общая сумма расходов: {expenses['total']:.2f}\n"
    report += f"🧾 Количество транзакций: {expenses['count']}\n\n"
    
    # Добавляем статистику по категориям
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
        report += f"{emoji} {category}: {amount:.2f} ({percentage:.1f}%)\n"
    
    # Добавляем статус бюджета
    budget_status = helpers.format_budget_status(user_id, month, year)
    report += f"\n{budget_status}"
    
    # Отправляем отчет
    update.message.reply_text(report)
    
    # Отправляем круговую диаграмму
    chart_path = visualization.create_monthly_pie_chart(user_id, month, year)
    if chart_path and os.path.exists(chart_path):
        with open(chart_path, 'rb') as photo:
            update.message.reply_photo(photo=photo, caption="Распределение расходов по категориям")
    
    # Отправляем сравнение с предыдущим месяцем, если возможно
    prev_month = month - 1
    prev_year = year
    if prev_month == 0:
        prev_month = 12
        prev_year = year - 1
    
    prev_expenses = excel.get_month_expenses(user_id, prev_month, prev_year)
    if prev_expenses and prev_expenses['total'] > 0:
        prev_month_name = helpers.get_month_name(prev_month)
        diff = expenses['total'] - prev_expenses['total']
        diff_percentage = (diff / prev_expenses['total']) * 100 if prev_expenses['total'] > 0 else 0
        
        comparison = f"📈 Сравнение с предыдущим месяцем:\n\n"
        comparison += f"{prev_month_name}: {prev_expenses['total']:.2f}\n"
        comparison += f"{month_name}: {expenses['total']:.2f}\n\n"
        
        if diff > 0:
            comparison += f"Увеличение расходов: +{diff:.2f} (+{diff_percentage:.1f}%)"
        else:
            comparison += f"Уменьшение расходов: {diff:.2f} ({diff_percentage:.1f}%)"
        
        update.message.reply_text(comparison)

def register_reminder_handlers(dp):
    """
    Регистрирует обработчики команд для напоминаний и альтернативных решений
    """
    dp.add_handler(CommandHandler("autostat", setup_monthly_reminder))
    dp.add_handler(CommandHandler("remind", remind_command))
    dp.add_handler(CommandHandler("monthend", end_of_month_stats))
