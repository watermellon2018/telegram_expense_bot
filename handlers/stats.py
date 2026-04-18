"""
Обработчики команд для получения статистики и анализа расходов
"""

import asyncio

from telegram import Update, ReplyKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import ContextTypes, CommandHandler, filters, MessageHandler, ConversationHandler, CallbackQueryHandler
from utils import excel, helpers, visualization, projects, incomes
from utils.helpers import main_menu_button_regex, analysis_menu_button_regex
from utils.logger import get_logger, log_command, log_event, log_error
import config
import os
import datetime
import time

logger = get_logger("handlers.stats")

# Состояния для ConversationHandler
CHOOSING_CATEGORY, = range(1)

async def month_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Обрабатывает команду /month для получения статистики за текущий месяц
    """
    from utils import budgets as budgets_utils
    from handlers.budget import _format_budget_status_text

    user_id = update.effective_user.id
    start_time = time.time()

    try:
        # Получаем текущий месяц и год
        now = datetime.datetime.now()
        month = now.month
        year = now.year

        # Получаем активный проект
        project_id = context.user_data.get('active_project_id')

        log_event(logger, "month_stats_requested", user_id=user_id,
                 project_id=project_id, month=month, year=year)

        # Получаем статистику расходов, доходов и бюджет параллельно
        expenses, month_incomes, budget = await asyncio.gather(
            excel.get_month_expenses(user_id, month, year, project_id),
            incomes.get_month_incomes(user_id, month, year, project_id),
            budgets_utils.get_or_inherit_budget(user_id, month, year, project_id),
        )

        if not expenses or expenses.get('total', 0) == 0:
            log_event(logger, "month_stats_empty", user_id=user_id,
                     project_id=project_id, month=month, year=year)

        # Форматируем расходную часть отчета
        report = helpers.format_month_expenses(expenses, month, year)

        # Добавляем сводку по доходам и итоговый баланс за месяц
        income_total = float(month_incomes.get('total', 0)) if month_incomes else 0.0
        expense_total = float(expenses.get('total', 0)) if expenses else 0.0
        net_total = income_total - expense_total
        report += (
            "\n\n💵 Доходы за месяц:\n"
            f"💰 Общая сумма доходов: {income_total:.2f}\n"
            f"📈 Чистый результат месяца: {net_total:.2f}"
        )

        # Добавляем статус бюджета (если задан)
        if budget:
            spending = float(expenses.get('total', 0)) if expenses else 0.0
            report += "\n\n" + _format_budget_status_text(budget, spending, month, year)

        # Добавляем информацию о проекте
        report = await helpers.add_project_context_to_report(report, user_id, project_id)

        # Отправляем отчет
        await update.message.reply_text(report, reply_markup=helpers.get_main_menu_keyboard())
        
        total = expense_total
        count = expenses.get('count', 0) if expenses else 0
        log_event(logger, "month_stats_sent", user_id=user_id, 
                 project_id=project_id, month=month, year=year,
                 total=total, income_total=income_total, net_total=net_total, count=count)

        # Если есть расходы, отправляем круговую диаграмму
        if expenses and expenses['total'] > 0:
            chart_start = time.time()
            chart_path = await visualization.create_monthly_pie_chart(user_id,
                                                                month=month,
                                                                year=year,
                                                                project_id=project_id)
            chart_duration = time.time() - chart_start
            
            if chart_path and os.path.exists(chart_path):
                with open(chart_path, 'rb') as photo:
                    await update.message.reply_photo(photo=photo, caption="Распределение расходов по категориям")
                log_event(logger, "month_chart_sent", user_id=user_id, 
                         project_id=project_id, month=month, year=year,
                         duration=chart_duration)
            else:
                log_event(logger, "month_chart_failed", user_id=user_id, 
                         project_id=project_id, month=month, year=year,
                         reason="chart_not_created")
        
        duration = time.time() - start_time
        log_event(logger, "month_command_success", user_id=user_id, 
                 project_id=project_id, duration=duration)
        
    except Exception as e:
        duration = time.time() - start_time
        log_error(logger, e, "month_command_error", user_id=user_id, duration=duration)
        await update.message.reply_text("❌ Произошла ошибка при получении статистики.")

async def category_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Обрабатывает команду /category для получения статистики по категории
    """
    from utils import categories
    
    user_id = update.effective_user.id

    # Проверяем, что указана категория
    if not context.args or len(context.args) < 1:
        # Получаем активный проект
        project_id = context.user_data.get('active_project_id')
        
        # Получаем доступные категории для пользователя
        await categories.ensure_system_categories_exist(user_id)
        cats = await categories.get_categories_for_user_project(user_id, project_id)
        
        if not cats:
            await update.message.reply_text("Нет доступных категорий.")
            return
        
        # Формируем список категорий
        categories_list_emoji = []
        for cat in cats:
            emoji = config.DEFAULT_CATEGORIES.get(cat['name'], '📦')
            categories_list_emoji.append(f"{emoji}  {cat['name'].title()}")
        
        message = 'Доступные категории:\n'
        message += '\n'.join(categories_list_emoji)
        
        await update.message.reply_text(
            message
        )
        return

    category_name = context.args[0].lower()

    # Получаем активный проект
    project_id = context.user_data.get('active_project_id')
    
    # Ищем категорию по имени одним SQL-запросом
    await categories.ensure_system_categories_exist(user_id)
    category_found = await categories.get_category_by_name(user_id, category_name, project_id)

    if not category_found:
        await update.message.reply_text(
            f"❌ Категория '{category_name}' не найдена."
        )
        return

    # Получаем текущий год
    year = datetime.datetime.now().year

    # Получаем статистику расходов по категории
    category_data = await excel.get_category_expenses(user_id, category_found['category_id'], year, project_id)

    # Форматируем отчет
    report = helpers.format_category_expenses(category_data, category_found['name'], year)
    
    # Добавляем информацию о проекте
    report = await helpers.add_project_context_to_report(report, user_id, project_id)

    # Отправляем отчет
    await update.message.reply_text(report, reply_markup=helpers.get_main_menu_keyboard())

    # Если есть расходы, отправляем график тренда
    if category_data and category_data['total'] > 0:
        chart_path = await visualization.create_category_trend_chart(user_id, category_found['name'], year)
        if chart_path and os.path.exists(chart_path):
            with open(chart_path, 'rb') as photo:
                await update.message.reply_photo(photo=photo, caption=f"Тренд расходов на {category_found['name']} за {year} год")

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Обрабатывает команду /stats для получения общей статистики расходов
    """
    user_id = update.effective_user.id
    project_id = context.user_data.get('active_project_id')

    # Получаем текущий год
    year = datetime.datetime.now().year

    # Генерируем графики параллельно
    category_chart, budget_chart, income_category_chart, income_vs_expense_chart = await asyncio.gather(
        visualization.create_category_distribution_chart(user_id, year),
        visualization.create_budget_comparison_chart(user_id, year, project_id=project_id),
        visualization.create_income_distribution_chart(user_id, year, project_id=project_id),
        visualization.create_income_vs_expense_chart(user_id, year, project_id=project_id),
    )

    # 1. Распределение по категориям
    if category_chart and os.path.exists(category_chart):
        with open(category_chart, 'rb') as photo:
            await update.message.reply_photo(photo=photo, caption=f"Распределение расходов по категориям за {year} год")

    # 2. Доходы по категориям
    if income_category_chart and os.path.exists(income_category_chart):
        with open(income_category_chart, 'rb') as photo:
            await update.message.reply_photo(photo=photo, caption=f"Распределение доходов по категориям за {year} год")

    # 3. Доходы vs расходы по месяцам
    if income_vs_expense_chart and os.path.exists(income_vs_expense_chart):
        with open(income_vs_expense_chart, 'rb') as photo:
            await update.message.reply_photo(photo=photo, caption=f"Доходы vs расходы по месяцам за {year} год")

    # 4. Бюджет vs. расходы (только если бюджет задан)
    if budget_chart and os.path.exists(budget_chart):
        with open(budget_chart, 'rb') as photo:
            await update.message.reply_photo(photo=photo, caption=f"Бюджет vs. расходы за {year} год")

async def handle_category_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Обрабатывает выбор категории для построения тренда
    """
    from utils import categories
    
    user_id = update.effective_user.id
    category_name = update.message.text

    if category_name == 'Отмена':
        await update.message.reply_text("Построение графика отменено.")
        return ConversationHandler.END

    # Получаем активный проект
    project_id = context.user_data.get('active_project_id')
    
    # Ищем категорию по имени одним SQL-запросом
    await categories.ensure_system_categories_exist(user_id)
    category_found = await categories.get_category_by_name(user_id, category_name, project_id)

    if not category_found:
        await update.message.reply_text(f"Категория '{category_name}' не найдена.")
        return ConversationHandler.END

    # Получаем текущий год
    year = datetime.datetime.now().year

    # Создаем график тренда
    chart_path = await visualization.create_category_trend_chart(user_id, category_found['name'], year)
    if chart_path and os.path.exists(chart_path):
        with open(chart_path, 'rb') as photo:
            await update.message.reply_photo(photo=photo, caption=f"Тренд расходов на {category_found['name']} за {year} год")
    else:
        await update.message.reply_text(f"Нет данных о расходах по категории '{category_found['name']}' за {year} год.")

    return ConversationHandler.END

# Отмена (необязательно)
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await helpers.cancel_conversation(update, context, "Действие отменено.")

async def day_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Команда /day для получения статистики за текущий день
    """
    user_id = update.effective_user.id
    
    # Получаем текущую дату
    date = datetime.datetime.now().strftime('%Y-%m-%d')
    
    # Получаем активный проект
    project_id = context.user_data.get('active_project_id')
    
    # Получаем статистику расходов
    expenses = await excel.get_day_expenses(user_id, date, project_id)
    
    # Форматируем отчет
    report = helpers.format_day_expenses(expenses, date)
    
    # Добавляем информацию о проекте
    report = await helpers.add_project_context_to_report(report, user_id, project_id)
    
    # Отправляем отчет
    await update.message.reply_text(report, reply_markup=helpers.get_main_menu_keyboard())
    

def register_stats_handlers(application):
    """
    Регистрирует обработчики команд для получения статистики и анализа
    """
    application.add_handler(CommandHandler("month", month_command))
    application.add_handler(MessageHandler(filters.Regex(main_menu_button_regex("month")), month_command))
    application.add_handler(CommandHandler("category", category_command))
    # Categories button now handled by category menu (handlers/category.py)
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(MessageHandler(filters.Regex(analysis_menu_button_regex("stats")), stats_command))
    application.add_handler(CommandHandler("day", day_command))
    application.add_handler(MessageHandler(filters.Regex(main_menu_button_regex("day")), day_command))
