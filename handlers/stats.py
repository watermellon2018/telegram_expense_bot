"""
Обработчики команд для получения статистики и анализа расходов
"""

from telegram import Update, ParseMode, ReplyKeyboardMarkup
from telegram.ext import CallbackContext, CommandHandler, Filters, MessageHandler, ConversationHandler, CallbackQueryHandler
from utils import excel, helpers, visualization
import config
import os
import datetime

# Состояния для ConversationHandler
CHOOSING_CATEGORY, ENTERING_BUDGET = range(2)

def month_command(update: Update, context: CallbackContext) -> None:
    """
    Обрабатывает команду /month для получения статистики за текущий месяц
    """
    user_id = update.effective_user.id

    # Получаем текущий месяц и год
    now = datetime.datetime.now()
    month = now.month
    year = now.year

    # Получаем статистику расходов
    expenses = excel.get_month_expenses(user_id, month, year)

    # Форматируем отчет
    report = helpers.format_month_expenses(expenses, month, year)

    # Отправляем отчет
    update.message.reply_text(report)

    # Если есть расходы, отправляем круговую диаграмму
    if expenses and expenses['total'] > 0:
        chart_path = visualization.create_monthly_pie_chart(user_id, month, year)
        if chart_path and os.path.exists(chart_path):
            with open(chart_path, 'rb') as photo:
                update.message.reply_photo(photo=photo, caption="Распределение расходов по категориям")

def category_command(update: Update, context: CallbackContext) -> None:
    """
    Обрабатывает команду /category для получения статистики по категории
    """
    user_id = update.effective_user.id

    # Проверяем, что указана категория
    if not context.args or len(context.args) < 1:
        # Отправляем список доступных категорий
        categories_list_emoji = [f"{emoji}  {category.title()}" for category, emoji in config.DEFAULT_CATEGORIES.items()]
        message = 'Доступные категории:\n'
        message += '\n'.join(categories_list_emoji)
        
        update.message.reply_text(
            message
        )
        return

    category = context.args[0].lower()

    # Проверяем, что категория существует
    if category not in config.DEFAULT_CATEGORIES:
        categories_list = ", ".join(config.DEFAULT_CATEGORIES.keys())
        update.message.reply_text(
            f"❌ Категория '{category}' не найдена.\n"
            f"Доступные категории: {categories_list}"
        )
        return

    # Получаем текущий год
    year = datetime.datetime.now().year

    # Получаем статистику расходов по категории
    category_data = excel.get_category_expenses(user_id, category, year)

    # Форматируем отчет
    report = helpers.format_category_expenses(category_data, category, year)

    # Отправляем отчет
    update.message.reply_text(report)

    # Если есть расходы, отправляем график тренда
    if category_data and category_data['total'] > 0:
        chart_path = visualization.create_category_trend_chart(user_id, category, year)
        if chart_path and os.path.exists(chart_path):
            with open(chart_path, 'rb') as photo:
                update.message.reply_photo(photo=photo, caption=f"Тренд расходов на {category} за {year} год")

def stats_command(update: Update, context: CallbackContext) -> None:
    """
    Обрабатывает команду /stats для получения общей статистики расходов
    """
    user_id = update.effective_user.id

    # Получаем текущий год
    year = datetime.datetime.now().year

    # Отправляем графики
    # 1. Распределение по категориям
    category_chart = visualization.create_category_distribution_chart(user_id, year)
    if category_chart and os.path.exists(category_chart):
        with open(category_chart, 'rb') as photo:
            update.message.reply_photo(photo=photo, caption=f"Распределение расходов по категориям за {year} год")

    # 2. Расходы по месяцам
    monthly_chart = visualization.create_monthly_bar_chart(user_id, year)
    if monthly_chart and os.path.exists(monthly_chart):
        with open(monthly_chart, 'rb') as photo:
            update.message.reply_photo(photo=photo, caption=f"Расходы по месяцам за {year} год")

    # 3. Сравнение с бюджетом
    budget_chart = visualization.create_budget_comparison_chart(user_id, year)
    if budget_chart and os.path.exists(budget_chart):
        with open(budget_chart, 'rb') as photo:
            update.message.reply_photo(photo=photo, caption=f"Сравнение бюджета и фактических расходов за {year} год")


def handle_category_choice(update: Update, context: CallbackContext) -> int:
    """
    Обрабатывает выбор категории для построения тренда
    """
    user_id = update.effective_user.id
    category = update.message.text

    if category == 'Отмена':
        update.message.reply_text("Построение графика отменено.")
        return ConversationHandler.END

    # Проверяем, что категория существует
    if category.lower() not in config.DEFAULT_CATEGORIES:
        update.message.reply_text(f"Категория '{category}' не найдена.")
        return ConversationHandler.END

    # Получаем текущий год
    year = datetime.datetime.now().year

    # Создаем график тренда
    chart_path = visualization.create_category_trend_chart(user_id, category.lower(), year)
    if chart_path and os.path.exists(chart_path):
        with open(chart_path, 'rb') as photo:
            update.message.reply_photo(photo=photo, caption=f"Тренд расходов на {category} за {year} год")
    else:
        update.message.reply_text(f"Нет данных о расходах по категории '{category}' за {year} год.")

    return ConversationHandler.END

def budget_command(update: Update, context: CallbackContext) -> int:
    """
    Обрабатывает команду /budget для установки бюджета на месяц
    """
    user_id = update.effective_user.id

    # Проверяем, что указана сумма
    if context.args and len(context.args) > 0:
        try:
            # Парсим сумму
            amount = float(context.args[0])

            # Получаем текущий месяц и год
            now = datetime.datetime.now()
            month = now.month
            year = now.year

            # Устанавливаем бюджет
            excel.set_budget(user_id, amount, month, year)

            # Отправляем подтверждение
            month_name = helpers.get_month_name(month)
            update.message.reply_text(
                f"✅ Бюджет на {month_name} {year} года установлен: {amount:.2f}"
            )
            return ConversationHandler.END
        except ValueError:
            update.message.reply_text(
                "❌ Неверный формат суммы. Используйте:\n"
                "/budget <сумма>\n"
                "Например: /budget 10000"
            )
            return ConversationHandler.END

    # Если сумма не указана, показываем текущий бюджет и запрашиваем новую сумму
    month = datetime.datetime.now().month
    year = datetime.datetime.now().year
    month_name = helpers.get_month_name(month)
    budget_status = helpers.format_budget_status(user_id, month, year)

    update.message.reply_text(
        f"{budget_status}\n\n"
        f"Введите сумму бюджета на {month_name} {year} года:"
    )

    return ENTERING_BUDGET

def handle_budget_amount(update: Update, context: CallbackContext) -> int:
    """
    Обрабатывает ввод суммы бюджета
    """
    user_id = update.effective_user.id
    text = update.message.text

    try:
        # Парсим сумму
        amount = float(text)

        # Получаем текущий месяц и год
        now = datetime.datetime.now()
        month = now.month
        year = now.year

        # Устанавливаем бюджет
        excel.set_budget(user_id, amount, month, year)

        # Отправляем подтверждение
        month_name = helpers.get_month_name(month)
        update.message.reply_text(
            f"✅ Бюджет на {month_name} {year} года установлен: {amount:.2f}"
        )
    except ValueError:
        update.message.reply_text(
            "❌ Неверный формат суммы. Пожалуйста, введите число.\n"
            "Например: 10000"
        )

    return ConversationHandler.END


# Отмена (необязательно)
def cancel(update: Update, context: CallbackContext):
    update.message.reply_text("Действие отменено.")
    return ConversationHandler.END

def day_command(update: Update, context: CallbackContext) -> None:
    """
    Команда /day для получения статистики за текущий день
    """
    user_id = update.effective_user.id
    
    # Получаем текущую дату
    date = datetime.datetime.now().strftime('%Y-%m-%d')
    
    # Получаем статистику расходов
    expenses = excel.get_day_expenses(user_id, date)
    
    # Форматируем отчет
    report = helpers.format_day_expenses(expenses, date)
    
    # Отправляем отчет
    update.message.reply_text(report)
    

def register_stats_handlers(dp):
    """
    Регистрирует обработчики команд для получения статистики и анализа
    """

    dp.add_handler(CommandHandler("month", month_command))
    dp.add_handler(CommandHandler("category", category_command))
    dp.add_handler(CommandHandler("stats", stats_command))
    dp.add_handler(CommandHandler("day", day_command))

    # Регистрируем ConversationHandler для команды /budget
    budget_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("budget", budget_command)],
        states={
            ENTERING_BUDGET: [MessageHandler(Filters.text & ~Filters.command, handle_budget_amount)],
        },
        fallbacks=[CommandHandler("cancel", lambda u, c: ConversationHandler.END)],
    )

    dp.add_handler(budget_conv_handler)
