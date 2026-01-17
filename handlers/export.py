"""
Обработчики команд для экспорта данных в Excel
"""
import config
from utils.export import get_month_name

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler
from utils import excel, projects, db
import os
import tempfile
import shutil
import pandas as pd
import datetime
from utils.logger import get_logger, log_event, log_error

logger = get_logger("handlers.export")


async def get_available_years(user_id: int, project_id: int = None) -> list:
    """
    Получает список доступных годов из базы данных для пользователя
    """
    project_id = excel._normalize_project_id(project_id) if hasattr(excel, '_normalize_project_id') else (project_id if project_id else None)
    
    try:
        rows = await db.fetch(
            """
            SELECT DISTINCT EXTRACT(YEAR FROM date)::int as year
            FROM expenses
            WHERE user_id = $1
              AND ((project_id IS NULL AND $2::int IS NULL) OR project_id = $2::int)
            ORDER BY year DESC
            """,
            str(user_id),
            project_id,
        )
        if not rows:
            log_event(logger, "get_years_empty", user_id=user_id, project_id=project_id)
            return []
        years = [int(row['year']) for row in rows]
        log_event(logger, "get_years_success", user_id=user_id, project_id=project_id, count=len(years))
        return years
    except Exception as e:
        log_error(logger, e, "get_years_error", user_id=user_id, project_id=project_id)
        return []


def create_main_export_menu() -> InlineKeyboardMarkup:
    """Создает главное меню экспорта"""
    keyboard = [
        [InlineKeyboardButton("📊 Экспорт всех расходов", callback_data="export:all")],
        [InlineKeyboardButton("📅 Экспорт за год", callback_data="export:year:select")],
        [InlineKeyboardButton("📆 Экспорт за месяц", callback_data="export:month:select_year")],
    ]
    return InlineKeyboardMarkup(keyboard)


def create_year_selection_menu(years: list, callback_prefix: str = "export:year") -> InlineKeyboardMarkup:
    """Создает меню выбора года"""
    keyboard = []
    # Группируем по 2 кнопки в ряд
    for i in range(0, len(years), 2):
        row = []
        row.append(InlineKeyboardButton(str(years[i]), callback_data=f"{callback_prefix}:{years[i]}"))
        if i + 1 < len(years):
            row.append(InlineKeyboardButton(str(years[i + 1]), callback_data=f"{callback_prefix}:{years[i + 1]}"))
        keyboard.append(row)
    
    # Кнопка "Назад"
    keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="export:main")])
    return InlineKeyboardMarkup(keyboard)


def create_month_selection_menu(year: int) -> InlineKeyboardMarkup:
    """Создает меню выбора месяца"""
    month_names = [
        "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
        "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"
    ]
    
    keyboard = []
    # Группируем по 3 месяца в ряд
    for i in range(0, 12, 3):
        row = []
        for j in range(3):
            if i + j < 12:
                month_num = i + j + 1
                row.append(InlineKeyboardButton(
                    month_names[i + j],
                    callback_data=f"export:month:{year}:{month_num}"
                ))
        keyboard.append(row)
    
    # Кнопка "Назад"
    keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="export:month:select_year")])
    return InlineKeyboardMarkup(keyboard)


async def export_stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Команда /export для экспорта статистики расходов в Excel.

    Если вызвана без аргументов - показывает интерактивное меню.
    Если вызвана с аргументами - выполняет экспорт напрямую.
    """
    from utils.logger import log_command
    
    user_id = update.effective_user.id
    project_id = context.user_data.get('active_project_id')
    
    log_command(logger, "export", user_id=user_id, project_id=project_id, has_args=bool(context.args))
    
    # Если есть аргументы - обрабатываем как раньше (для обратной совместимости)
    if context.args:
        year = None
        month = None
        
        if len(context.args) >= 1:
            try:
                year = int(context.args[0])
            except ValueError:
                await update.message.reply_text(
                    "❌ Неверный формат года. Используйте: /export [год] [месяц]\n"
                    "Например: /export 2024 или /export 2024 июнь"
                )
                return
        
        if len(context.args) >= 2:
            month_arg = context.args[1].lower()
            try:
                month = int(month_arg)
                if month < 1 or month > 12:
                    await update.message.reply_text("❌ Месяц должен быть от 1 до 12.")
                    return
            except ValueError:
                if month_arg in config.MONTH_NAMES:
                    month = config.MONTH_NAMES[month_arg]
                else:
                    available_months = ", ".join([f"{num} ({name})" for name, num in config.MONTH_NAMES.items() if len(name) > 3 or name=='май'])
                    await update.message.reply_text(
                        f"❌ Неизвестный месяц '{month_arg}'.\n"
                        f"Доступные варианты: {available_months}\n"
                        f"Или используйте числа от 1 до 12."
                    )
                    return
        
        # Выполняем экспорт напрямую
        await perform_export(update, user_id, project_id, year, month)
    else:
        # Показываем интерактивное меню
        menu = create_main_export_menu()
        await update.message.reply_text(
            "📊 Выберите тип экспорта:",
            reply_markup=menu
        )


async def perform_export(update: Update, user_id: int, project_id: int, year: int = None, month: int = None) -> None:
    """
    Выполняет экспорт данных в Excel файл
    """
    import time
    start_time = time.time()
    
    log_event(logger, "export_start", user_id=user_id, project_id=project_id, year=year, month=month)
    
    # Определяем, откуда пришел запрос - из сообщения или callback query
    if update.callback_query:
        message = update.callback_query.message
    else:
        message = update.message
    
    # Получаем все данные
    expenses_df = await excel.get_all_expenses(user_id, year, project_id)
    
    if expenses_df is None or expenses_df.empty:
        log_event(logger, "export_no_data", user_id=user_id, project_id=project_id, year=year, month=month)
        if year:
            await message.reply_text(f"❌ Нет данных за {year} год.")
        else:
            await message.reply_text("❌ У вас пока нет данных о расходах.")
        return
    
    # Конвертируем amount в numeric, если это необходимо
    if 'amount' in expenses_df.columns:
        expenses_df['amount'] = pd.to_numeric(expenses_df['amount'], errors='coerce')
    
    # Фильтруем по месяцу, если указан
    if month:
        expenses_df = expenses_df[expenses_df['month'] == month]
        if expenses_df.empty:
            month_name = get_month_name(month)
            await message.reply_text(f"❌ Нет данных за {month_name} {year} года.")
            return
    
    try:
        # Создаем временный файл со статистикой
        with tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx') as tmp_file:
            tmp_path = tmp_file.name
        
        # Создаем Excel файл со статистикой
        with pd.ExcelWriter(tmp_path, engine='openpyxl') as writer:
            # Основные данные
            expenses_df.to_excel(writer, sheet_name='Все расходы', index=False)
            
            # Статистика по категориям
            if not expenses_df.empty:
                category_stats = expenses_df.groupby('category')['amount'].agg(['sum', 'count', 'mean']).round(2)
                category_stats.columns = ['Общая сумма', 'Количество', 'Средняя сумма']
                category_stats.to_excel(writer, sheet_name='Статистика по категориям')
                
                # Статистика по месяцам (если не фильтруем по месяцу)
                if not month:
                    monthly_stats = expenses_df.groupby('month')['amount'].agg(['sum', 'count', 'mean']).round(2)
                    monthly_stats.columns = ['Общая сумма', 'Количество', 'Средняя сумма']
                    monthly_stats.to_excel(writer, sheet_name='Статистика по месяцам')
                
                # Статистика по дням (если фильтруем по месяцу)
                if month:
                    # Добавляем день из даты
                    expenses_df['day'] = pd.to_datetime(expenses_df['date']).dt.day
                    daily_stats = expenses_df.groupby('day')['amount'].agg(['sum', 'count', 'mean']).round(2)
                    daily_stats.columns = ['Общая сумма', 'Количество', 'Средняя сумма']
                    daily_stats.to_excel(writer, sheet_name='Статистика по дням')
                
                # Топ-10 самых дорогих расходов
                top_expenses = expenses_df.nlargest(10, 'amount')[['date', 'category', 'amount', 'description']]
                top_expenses.to_excel(writer, sheet_name='Топ-10 расходов', index=False)
                
                # Общая статистика
                total_amount = expenses_df['amount'].sum()
                total_count = len(expenses_df)
                avg_amount = expenses_df['amount'].mean()
                
                summary_stats = pd.DataFrame({
                    'Показатель': ['Общая сумма', 'Количество расходов', 'Средняя сумма', 'Максимальная сумма', 'Минимальная сумма'],
                    'Значение': [total_amount, total_count, avg_amount, expenses_df['amount'].max(), expenses_df['amount'].min()]
                })
                summary_stats.to_excel(writer, sheet_name='Общая статистика', index=False)
        
        # Отправляем файл
        with open(tmp_path, 'rb') as file:
            if month:
                month_name = get_month_name(month)
                filename = f"Статистика расходов за {month:02d}.{year}.xlsx"
                caption = f"📈 Статистика расходов за {month_name} {year} года\n\nФайл содержит детальную статистику ваших расходов."
            elif year:
                filename = f"Статистика расходов за {year} год.xlsx"
                caption = f"📈 Статистика расходов за {year} год\n\nФайл содержит детальную статистику ваших расходов."
            else:
                filename = "Общая статистика расходов.xlsx"
                caption = "📈 Статистика всех расходов\n\nФайл содержит детальную статистику ваших расходов."
            
            # Добавляем информацию о проекте
            if project_id is not None:
                project = await projects.get_project_by_id(user_id, project_id)
                if project:
                    caption = f"📁 Проект: {project['project_name']}\n\n{caption}"
            else:
                caption = f"📊 Общие расходы\n\n{caption}"
            
            await message.reply_document(
                document=file,
                filename=filename,
                caption=caption
            )
        
        # Удаляем временный файл
        os.unlink(tmp_path)
        
        duration = time.time() - start_time
        log_event(logger, "export_success", user_id=user_id, project_id=project_id, 
                 year=year, month=month, duration=duration, filename=filename)
        
    except Exception as e:
        duration = time.time() - start_time
        log_error(logger, e, "export_error", user_id=user_id, project_id=project_id, 
                 year=year, month=month, duration=duration)
        await message.reply_text(f"❌ Ошибка при создании статистики: {str(e)}")
        # Очищаем временный файл в случае ошибки
        if 'tmp_path' in locals():
            try:
                os.unlink(tmp_path)
            except:
                pass


async def handle_export_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Обрабатывает нажатия на inline-кнопки меню экспорта
    """
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    project_id = context.user_data.get('active_project_id')
    callback_data = query.data
    
    # Парсим callback_data: export:action:params
    parts = callback_data.split(':')
    action = parts[1] if len(parts) > 1 else None
    
    if action == "main":
        # Показываем главное меню
        menu = create_main_export_menu()
        await query.edit_message_text("📊 Выберите тип экспорта:", reply_markup=menu)
    
    elif action == "all":
        # Экспорт всех расходов
        await query.edit_message_text("⏳ Генерирую файл со всеми расходами...")
        await perform_export(update, user_id, project_id, year=None, month=None)
        await query.delete_message()
    
    elif action == "year":
        if len(parts) == 3 and parts[2] == "select":
            # Показываем выбор года
            years = await get_available_years(user_id, project_id)
            if not years:
                await query.edit_message_text("❌ У вас пока нет данных о расходах.")
                return
            
            menu = create_year_selection_menu(years)
            await query.edit_message_text("📅 Выберите год:", reply_markup=menu)
        elif len(parts) == 3:
            # Выбран год - выполняем экспорт
            try:
                year = int(parts[2])
                await query.edit_message_text(f"⏳ Генерирую файл за {year} год...")
                await perform_export(update, user_id, project_id, year=year, month=None)
                await query.delete_message()
            except ValueError:
                await query.edit_message_text("❌ Ошибка: неверный формат года.")
    
    elif action == "month":
        if len(parts) == 3 and parts[2] == "select_year":
            # Показываем выбор года для месяца
            years = await get_available_years(user_id, project_id)
            if not years:
                await query.edit_message_text("❌ У вас пока нет данных о расходах.")
                return
            
            menu = create_year_selection_menu(years, callback_prefix="export:month:year")
            await query.edit_message_text("📅 Выберите год для экспорта по месяцам:", reply_markup=menu)
        elif len(parts) == 4 and parts[2] == "year":
            # Выбран год - показываем выбор месяца
            try:
                year = int(parts[3])
                menu = create_month_selection_menu(year)
                await query.edit_message_text(f"📆 Выберите месяц для {year} года:", reply_markup=menu)
            except ValueError:
                await query.edit_message_text("❌ Ошибка: неверный формат года.")
        elif len(parts) == 4:
            # Выбраны год и месяц - выполняем экспорт
            try:
                year = int(parts[2])
                month = int(parts[3])
                month_name = get_month_name(month)
                await query.edit_message_text(f"⏳ Генерирую файл за {month_name} {year} года...")
                await perform_export(update, user_id, project_id, year=year, month=month)
                await query.delete_message()
            except (ValueError, IndexError):
                await query.edit_message_text("❌ Ошибка: неверный формат данных.")


def register_export_handlers(application):
    """
    Регистрирует обработчики команд для экспорта
    """
    application.add_handler(CommandHandler("export", export_stats_command))
    application.add_handler(CallbackQueryHandler(handle_export_callback, pattern="^export:"))