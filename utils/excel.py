"""
Утилиты для работы с Excel-файлами
"""

import os
import pandas as pd
import datetime
from openpyxl import Workbook
from openpyxl.utils.dataframe import dataframe_to_rows
import config

def create_user_dir(user_id):
    """
    Создает директорию для хранения данных пользователя
    """
    user_dir = os.path.join(config.DATA_DIR, str(user_id))
    if not os.path.exists(user_dir):
        os.makedirs(user_dir)
    return user_dir

def get_excel_path(user_id, year=None):
    """
    Возвращает путь к Excel-файлу для указанного года
    Если год не указан, используется текущий год
    """
    if year is None:
        year = datetime.datetime.now().year
    
    user_dir = create_user_dir(user_id)
    return os.path.join(user_dir, f"{year}.xlsx")

def create_excel_file(user_id, year=None):
    """
    Создает новый Excel-файл для указанного года с нужной структурой
    """
    if year is None:
        year = datetime.datetime.now().year
    
    excel_path = get_excel_path(user_id, year)
    
    # Создаем новый файл только если он не существует
    if not os.path.exists(excel_path):
        # Создаем пустой DataFrame для расходов
        expenses_df = pd.DataFrame(columns=[
            'date', 'time', 'amount', 'category', 'description', 'month'
        ])
        
        # Создаем DataFrame для категорий
        categories_df = pd.DataFrame({
            'category_name': list(config.DEFAULT_CATEGORIES.keys()),
            'emoji': list(config.DEFAULT_CATEGORIES.values())
        })
        
        # Создаем DataFrame для бюджета
        budget_df = pd.DataFrame({
            'month': list(range(1, 13)),
            'budget': [0] * 12,
            'actual': [0] * 12
        })
        
        # Сохраняем все в Excel
        with pd.ExcelWriter(excel_path, engine='openpyxl') as writer:
            expenses_df.to_excel(writer, sheet_name='Expenses', index=False)
            categories_df.to_excel(writer, sheet_name='Categories', index=False)
            budget_df.to_excel(writer, sheet_name='Budget', index=False)
    
    return excel_path

def add_expense(user_id, amount, category, description=""):
    """
    Добавляет новый расход в Excel-файл
    """
    now = datetime.datetime.now()
    year = now.year
    month = now.month
    date_str = now.strftime('%Y-%m-%d')
    time_str = now.strftime('%H:%M:%S')
    
    # Получаем путь к файлу и создаем его, если не существует
    excel_path = create_excel_file(user_id, year)
    
    # Сначала читаем все данные из файла
    try:
        # Загружаем текущие данные
        expenses_df = pd.read_excel(excel_path, sheet_name='Expenses', engine='openpyxl')
        budget_df = pd.read_excel(excel_path, sheet_name='Budget', engine='openpyxl')
        categories_df = pd.read_excel(excel_path, sheet_name='Categories', engine='openpyxl')
        
        # Добавляем новую запись
        new_expense = pd.DataFrame({
            'date': [date_str],
            'time': [time_str],
            'amount': [float(amount)],
            'category': [category.lower()],
            'description': [description],
            'month': [month]
        })
        
        expenses_df = pd.concat([expenses_df, new_expense], ignore_index=True)
        
        # Обновляем фактические расходы в бюджете
        month_expenses = expenses_df[expenses_df['month'] == month]['amount'].sum()
        budget_df.loc[budget_df['month'] == month, 'actual'] = month_expenses
        
        # Затем записываем все данные обратно в файл
        with pd.ExcelWriter(excel_path, engine='openpyxl') as writer:
            expenses_df.to_excel(writer, sheet_name='Expenses', index=False)
            budget_df.to_excel(writer, sheet_name='Budget', index=False)
            categories_df.to_excel(writer, sheet_name='Categories', index=False)
        
        return True
    except Exception as e:
        print(f"Ошибка при добавлении расхода: {e}")
        return False

def get_month_expenses(user_id, month=None, year=None):
    """
    Возвращает статистику расходов за указанный месяц
    """
    if month is None:
        month = datetime.datetime.now().month
    if year is None:
        year = datetime.datetime.now().year
    
    excel_path = get_excel_path(user_id, year)
    
    # Проверяем, существует ли файл
    if not os.path.exists(excel_path):
        return None
    
    try:
        # Загружаем данные
        expenses_df = pd.read_excel(excel_path, sheet_name='Expenses', engine='openpyxl')
        
        # Фильтруем по месяцу
        month_data = expenses_df[expenses_df['month'] == month]
        
        # Если данных нет, возвращаем пустой результат
        if month_data.empty:
            return {
                'total': 0,
                'by_category': {},
                'count': 0
            }
        
        # Рассчитываем статистику
        total = month_data['amount'].sum()
        by_category = month_data.groupby('category')['amount'].sum().to_dict()
        count = len(month_data)
        
        return {
            'total': total,
            'by_category': by_category,
            'count': count
        }
    except Exception as e:
        print(f"Ошибка при получении статистики за месяц: {e}")
        return None

def set_budget(user_id, amount, month=None, year=None):
    """
    Устанавливает бюджет на указанный месяц
    """
    if month is None:
        month = datetime.datetime.now().month
    if year is None:
        year = datetime.datetime.now().year
    
    # Получаем путь к файлу и создаем его, если не существует
    excel_path = create_excel_file(user_id, year)
    
    try:
        # Сначала читаем все данные из файла
        budget_df = pd.read_excel(excel_path, sheet_name='Budget', engine='openpyxl')
        expenses_df = pd.read_excel(excel_path, sheet_name='Expenses', engine='openpyxl')
        categories_df = pd.read_excel(excel_path, sheet_name='Categories', engine='openpyxl')
        
        # Обновляем бюджет для указанного месяца
        budget_df.loc[budget_df['month'] == month, 'budget'] = float(amount)
        
        # Затем записываем все данные обратно в файл
        with pd.ExcelWriter(excel_path, engine='openpyxl') as writer:
            budget_df.to_excel(writer, sheet_name='Budget', index=False)
            expenses_df.to_excel(writer, sheet_name='Expenses', index=False)
            categories_df.to_excel(writer, sheet_name='Categories', index=False)
        
        return True
    except Exception as e:
        print(f"Ошибка при установке бюджета: {e}")
        return False

def get_category_expenses(user_id, category, year=None):
    """
    Возвращает статистику расходов по указанной категории за год
    """
    if year is None:
        year = datetime.datetime.now().year
    
    excel_path = get_excel_path(user_id, year)
    
    # Проверяем, существует ли файл
    if not os.path.exists(excel_path):
        return None
    
    try:
        # Загружаем данные
        expenses_df = pd.read_excel(excel_path, sheet_name='Expenses', engine='openpyxl')
        
        # Фильтруем по категории
        category_data = expenses_df[expenses_df['category'] == category.lower()]
        
        # Если данных нет, возвращаем пустой результат
        if category_data.empty:
            return {
                'total': 0,
                'by_month': {},
                'count': 0
            }
        
        # Рассчитываем статистику
        total = category_data['amount'].sum()
        by_month = category_data.groupby('month')['amount'].sum().to_dict()
        count = len(category_data)
        
        return {
            'total': total,
            'by_month': by_month,
            'count': count
        }
    except Exception as e:
        print(f"Ошибка при получении статистики по категории: {e}")
        return None

def get_all_expenses(user_id, year=None):
    """
    Возвращает все расходы за указанный год
    """
    if year is None:
        year = datetime.datetime.now().year
    
    excel_path = get_excel_path(user_id, year)
    
    # Проверяем, существует ли файл
    if not os.path.exists(excel_path):
        return None
    
    try:
        # Загружаем данные
        expenses_df = pd.read_excel(excel_path, sheet_name='Expenses', engine='openpyxl')
        return expenses_df
    except Exception as e:
        print(f"Ошибка при получении всех расходов: {e}")
        return None


def get_day_expenses(user_id, date=None):
    """
    Возвращает статистику расходов за указанный день
    """
    if date is None:
        date = datetime.datetime.now().strftime('%Y-%m-%d')
    
    year = int(date.split('-')[0])
    month = int(date.split('-')[1])
    day = int(date.split('-')[2])
    
    excel_path = get_excel_path(user_id, year)
    
    # Проверяем, существует ли файл
    if not os.path.exists(excel_path):
        return None
    
    try:
        # Загружаем данные
        expenses_df = pd.read_excel(excel_path, sheet_name='Expenses', engine='openpyxl')
        
        # Проверяем, существует ли столбец 'date'
        if 'date' not in expenses_df.columns:
            return {
                'status': False,
                'note': 'Нет данных'
            }
        
        # Фильтруем по дате
        day_data = expenses_df[expenses_df['date'] == date]
        
        
        # Если данных нет, возвращаем пустой результат
        if day_data.empty:
            return {
                'status': True,
                'total': 0,
                'by_category': {},
                'count': 0
            }
        
        # Рассчитываем статистику
        total = day_data['amount'].sum()
        by_category = day_data.groupby('category')['amount'].sum().to_dict()
        count = len(day_data)
        
        return {
            'status': True,
            'total': total,
            'by_category': by_category,
            'count': count
        }
    except Exception as e:
        print(f"Error getting daily statistics: {e}")
        return None
