"""
Обработчики команд для экспорта данных в Excel
"""
import config
from utils.export import get_month_name

from telegram import Update
from telegram.ext import CallbackContext, CommandHandler
from utils import excel
import os
import tempfile
import shutil
import pandas as pd


def export_excel_command(update: Update, context: CallbackContext) -> None:
    """
    Обрабатывает команду /export для отправки Excel файла с данными пользователя
    """
    user_id = update.effective_user.id
    
    # Получаем активный проект
    project_id = context.user_data.get('active_project_id')
    
    # Получаем год из аргументов команды или используем текущий
    year = None
    if context.args:
        try:
            year = int(context.args[0])
        except ValueError:
            update.message.reply_text(
                "❌ Неверный формат года. Используйте: /export [год]\n"
                "Например: /export 2024"
            )
            return
    
    # Берём данные из БД и формируем временный Excel "на лету"
    expenses_df = excel.get_all_expenses(user_id, year, project_id)

    if expenses_df is None or expenses_df.empty:
        if year:
            update.message.reply_text(f"❌ Нет данных за {year} год.")
        else:
            update.message.reply_text("❌ У вас пока нет данных о расходах.")
        return
    
    # Конвертируем amount в numeric, если это необходимо
    if 'amount' in expenses_df.columns:
        expenses_df['amount'] = pd.to_numeric(expenses_df['amount'], errors='coerce')

    try:
        # Создаем временный Excel файл
        with tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx') as tmp_file:
            tmp_path = tmp_file.name

        # Записываем данные в Excel
        with pd.ExcelWriter(tmp_path, engine='openpyxl') as writer:
            expenses_df.to_excel(writer, sheet_name='Expenses', index=False)

        # Отправляем файл
        with open(tmp_path, 'rb') as file:
            year_text = f" за {year} год" if year else ""
            
            # Добавляем информацию о проекте
            if project_id is not None:
                from utils import projects
                project = projects.get_project_by_id(user_id, project_id)
                if project:
                    caption = f"📁 Проект: {project['project_name']}\n📊 Расходы{year_text}\n\nФайл содержит все записи о расходах проекта."
                else:
                    caption = f"📊 Ваши расходы{year_text}\n\nФайл содержит все ваши записи о расходах с детальной статистикой."
            else:
                caption = f"📊 Общие расходы{year_text}\n\nФайл содержит все ваши записи о расходах с детальной статистикой."
            
            update.message.reply_document(
                document=file,
                filename=f"expenses{year_text}.xlsx",
                caption=caption
            )
        
        # Удаляем временный файл
        os.unlink(tmp_path)
        
    except Exception as e:
        update.message.reply_text(f"❌ Ошибка при отправке файла: {str(e)}")
        # Очищаем временный файл в случае ошибки
        if 'tmp_path' in locals():
            try:
                os.unlink(tmp_path)
            except:
                pass


def export_stats_command(update: Update, context: CallbackContext) -> None:
    """
    Обрабатывает команду /export_stats для отправки Excel файла со статистикой
    Поддерживает: /export_stats [год] [месяц]
    Месяц можно указать числом (1-12) или названием (январь, февраль, март, и т.д.)
    """
    user_id = update.effective_user.id
    
    # Получаем год и месяц из аргументов команды
    year = None
    month = None
    
    if len(context.args) >= 1:
        try:
            year = int(context.args[0])
        except ValueError:
            update.message.reply_text(
                "❌ Неверный формат года. Используйте: /export_stats [год] [месяц]\n"
                "Например: /export_stats 2024 или /export_stats 2024 июнь"
            )
            return
    
    if len(context.args) >= 2:
        month_arg = context.args[1].lower()
        
        # Сначала пытаемся распарсить как число
        try:
            month = int(month_arg)
            if month < 1 or month > 12:
                update.message.reply_text("❌ Месяц должен быть от 1 до 12.")
                return
        except ValueError:
            # Если не число, пытаемся найти в словаре названий
            if month_arg in config.MONTH_NAMES:
                month = config.MONTH_NAMES[month_arg]
            else:
                available_months = ", ".join([f"{num} ({name})" for name, num in config.MONTH_NAMES.items() if len(name) > 3 or name=='май'])
                update.message.reply_text(
                    f"❌ Неизвестный месяц '{month_arg}'.\n"
                    f"Доступные варианты: {available_months}\n"
                    f"Или используйте числа от 1 до 12."
                )
                return
    
    # Получаем все данные
    expenses_df = excel.get_all_expenses(user_id, year)
    
    if expenses_df is None or expenses_df.empty:
        if year:
            update.message.reply_text(f"❌ Нет данных за {year} год.")
        else:
            update.message.reply_text("❌ У вас пока нет данных о расходах.")
        return
    
    # Конвертируем amount в numeric, если это необходимо
    if 'amount' in expenses_df.columns:
        expenses_df['amount'] = pd.to_numeric(expenses_df['amount'], errors='coerce')
    
    # Фильтруем по месяцу, если указан
    if month:
        expenses_df = expenses_df[expenses_df['month'] == month]
        if expenses_df.empty:
            month_name = get_month_name(month)
            update.message.reply_text(f"❌ Нет данных за {month_name} {year} года.")
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
                filename = f"expense_stats_{year}_{month:02d}.xlsx"
                caption = f"📈 Статистика расходов за {month_name} {year} года\n\nФайл содержит детальную статистику ваших расходов."
            elif year:
                filename = f"expense_stats_{year}.xlsx"
                caption = f"📈 Статистика расходов за {year} год\n\nФайл содержит детальную статистику ваших расходов."
            else:
                filename = "expense_stats_all.xlsx"
                caption = "📈 Статистика всех расходов\n\nФайл содержит детальную статистику ваших расходов."
            
            update.message.reply_document(
                document=file,
                filename=filename,
                caption=caption
            )
        
        # Удаляем временный файл
        os.unlink(tmp_path)
        
    except Exception as e:
        update.message.reply_text(f"❌ Ошибка при создании статистики: {str(e)}")
        # Очищаем временный файл в случае ошибки
        if 'tmp_path' in locals():
            try:
                os.unlink(tmp_path)
            except:
                pass


def register_export_handlers(dp):
    """
    Регистрирует обработчики команд для экспорта
    """
    dp.add_handler(CommandHandler("export", export_excel_command))
    dp.add_handler(CommandHandler("export_stats", export_stats_command))
