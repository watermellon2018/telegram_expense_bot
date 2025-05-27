"""
Утилиты для визуализации данных расходов
"""

import os
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib
matplotlib.use('Agg')  # Использование не-интерактивного бэкенда
import seaborn as sns
import datetime
from utils import excel
import config

def create_monthly_pie_chart(user_id, month=None, year=None, save_path=None):
    """
    Создает круговую диаграмму расходов по категориям за указанный месяц
    """
    if month is None:
        month = datetime.datetime.now().month
    if year is None:
        year = datetime.datetime.now().year
    
    # Получаем данные о расходах
    expenses = excel.get_month_expenses(user_id, month, year)
    
    if not expenses or expenses['total'] == 0:
        return None
    
    # Подготавливаем данные для диаграммы
    categories = []
    amounts = []
    colors = []
    
    # Сортируем категории по убыванию сумм
    sorted_categories = sorted(
        expenses['by_category'].items(), 
        key=lambda x: x[1], 
        reverse=True
    )
    
    # Ограничиваем количество категорий для отображения
    if len(sorted_categories) > config.MAX_CATEGORIES_ON_CHART:
        main_categories = sorted_categories[:config.MAX_CATEGORIES_ON_CHART-1]
        other_sum = sum(item[1] for item in sorted_categories[config.MAX_CATEGORIES_ON_CHART-1:])
        
        for category, amount in main_categories:
            categories.append(f"{category} ({config.DEFAULT_CATEGORIES.get(category, '')})")
            amounts.append(amount)
            colors.append(config.COLORS.get(category, "#9E9E9E"))
        
        # Добавляем "Прочее"
        if other_sum > 0:
            categories.append("прочее")
            amounts.append(other_sum)
            colors.append("#9E9E9E")
    else:
        for category, amount in sorted_categories:
            categories.append(f"{category} ({config.DEFAULT_CATEGORIES.get(category, '')})")
            amounts.append(amount)
            colors.append(config.COLORS.get(category, "#9E9E9E"))
    
    # Создаем диаграмму
    plt.figure(figsize=(10, 7))
    plt.pie(amounts, labels=categories, autopct='%1.1f%%', startangle=90, colors=colors)
    plt.axis('equal')
    
    month_name = datetime.date(year, month, 1).strftime('%B')
    plt.title(f'Расходы за {month_name} {year}')
    
    # Сохраняем диаграмму
    if save_path is None:
        user_dir = excel.create_user_dir(user_id)
        save_path = os.path.join(user_dir, f"pie_chart_{year}_{month}.png")
    
    plt.savefig(save_path, bbox_inches='tight')
    plt.close()
    
    return save_path

def create_monthly_bar_chart(user_id, year=None, save_path=None):
    """
    Создает столбчатую диаграмму расходов по месяцам за указанный год
    """
    if year is None:
        year = datetime.datetime.now().year
    
    # Получаем данные о расходах
    excel_path = excel.get_excel_path(user_id, year)
    
    if not os.path.exists(excel_path):
        return None
    
    # Загружаем данные
    expenses_df = pd.read_excel(excel_path, sheet_name='Expenses')
    
    if expenses_df.empty:
        return None
    
    # Группируем данные по месяцам
    monthly_expenses = expenses_df.groupby('month')['amount'].sum()
    
    # Создаем список месяцев для отображения
    months = []
    for i in range(1, 13):
        month_name = datetime.date(year, i, 1).strftime('%b')
        months.append(month_name)
    
    # Подготавливаем данные для диаграммы
    amounts = []
    for i in range(1, 13):
        if i in monthly_expenses.index:
            amounts.append(monthly_expenses[i])
        else:
            amounts.append(0)
    
    # Создаем диаграмму
    plt.figure(figsize=(12, 6))
    bars = plt.bar(months, amounts, color='#2196F3')
    
    # Добавляем значения над столбцами
    for bar in bars:
        height = bar.get_height()
        if height > 0:
            plt.text(bar.get_x() + bar.get_width()/2., height + 5,
                    f'{int(height)}',
                    ha='center', va='bottom')
    
    plt.title(f'Расходы по месяцам за {year} год')
    plt.xlabel('Месяц')
    plt.ylabel('Сумма')
    plt.grid(axis='y', linestyle='--', alpha=0.7)
    
    # Сохраняем диаграмму
    if save_path is None:
        user_dir = excel.create_user_dir(user_id)
        save_path = os.path.join(user_dir, f"bar_chart_{year}.png")
    
    plt.savefig(save_path, bbox_inches='tight')
    plt.close()
    
    return save_path

def create_category_trend_chart(user_id, category, year=None, save_path=None):
    """
    Создает график тренда расходов по указанной категории за год
    """
    if year is None:
        year = datetime.datetime.now().year
    
    # Получаем данные о расходах по категории
    category_data = excel.get_category_expenses(user_id, category, year)
    
    if not category_data or category_data['total'] == 0:
        return None
    
    # Подготавливаем данные для графика
    months = []
    amounts = []
    
    for i in range(1, 13):
        month_name = datetime.date(year, i, 1).strftime('%b')
        months.append(month_name)
        
        if i in category_data['by_month']:
            amounts.append(category_data['by_month'][i])
        else:
            amounts.append(0)
    
    # Создаем график
    plt.figure(figsize=(12, 6))
    plt.plot(months, amounts, marker='o', linestyle='-', color=config.COLORS.get(category.lower(), "#2196F3"), linewidth=2)
    
    # Добавляем значения над точками
    for i, amount in enumerate(amounts):
        if amount > 0:
            plt.text(i, amount + 5, f'{int(amount)}', ha='center')
    
    plt.title(f'Расходы на {category} за {year} год')
    plt.xlabel('Месяц')
    plt.ylabel('Сумма')
    plt.grid(True, linestyle='--', alpha=0.7)
    
    # Сохраняем график
    if save_path is None:
        user_dir = excel.create_user_dir(user_id)
        save_path = os.path.join(user_dir, f"trend_{category}_{year}.png")
    
    plt.savefig(save_path, bbox_inches='tight')
    plt.close()
    
    return save_path

def create_budget_comparison_chart(user_id, year=None, save_path=None):
    """
    Создает график сравнения бюджета и фактических расходов по месяцам
    """
    if year is None:
        year = datetime.datetime.now().year
    
    # Получаем данные о бюджете
    excel_path = excel.get_excel_path(user_id, year)
    
    if not os.path.exists(excel_path):
        return None
    
    # Загружаем данные
    budget_df = pd.read_excel(excel_path, sheet_name='Budget')
    
    if budget_df.empty:
        return None
    
    # Создаем список месяцев для отображения
    months = []
    for i in range(1, 13):
        month_name = datetime.date(year, i, 1).strftime('%b')
        months.append(month_name)
    
    # Подготавливаем данные для графика
    budget_amounts = []
    actual_amounts = []
    
    for i in range(1, 13):
        month_data = budget_df[budget_df['month'] == i]
        if not month_data.empty:
            budget_amounts.append(month_data['budget'].values[0])
            actual_amounts.append(month_data['actual'].values[0])
        else:
            budget_amounts.append(0)
            actual_amounts.append(0)
    
    # Создаем график
    plt.figure(figsize=(12, 6))
    
    x = range(len(months))
    width = 0.35
    
    plt.bar([i - width/2 for i in x], budget_amounts, width, label='Бюджет', color='#4CAF50')
    plt.bar([i + width/2 for i in x], actual_amounts, width, label='Факт', color='#F44336')
    
    plt.xlabel('Месяц')
    plt.ylabel('Сумма')
    plt.title(f'Сравнение бюджета и фактических расходов за {year} год')
    plt.xticks(x, months)
    plt.legend()
    plt.grid(axis='y', linestyle='--', alpha=0.7)
    
    # Сохраняем график
    if save_path is None:
        user_dir = excel.create_user_dir(user_id)
        save_path = os.path.join(user_dir, f"budget_comparison_{year}.png")
    
    plt.savefig(save_path, bbox_inches='tight')
    plt.close()
    
    return save_path

def create_category_distribution_chart(user_id, year=None, save_path=None):
    """
    Создает горизонтальную столбчатую диаграмму распределения расходов по категориям за год
    """
    if year is None:
        year = datetime.datetime.now().year
    
    # Получаем данные о расходах
    excel_path = excel.get_excel_path(user_id, year)
    
    if not os.path.exists(excel_path):
        return None
    
    # Загружаем данные
    expenses_df = pd.read_excel(excel_path, sheet_name='Expenses')
    
    if expenses_df.empty:
        return None
    
    # Группируем данные по категориям
    category_expenses = expenses_df.groupby('category')['amount'].sum().sort_values(ascending=False)
    
    # Ограничиваем количество категорий для отображения
    if len(category_expenses) > config.MAX_CATEGORIES_ON_CHART:
        main_categories = category_expenses.iloc[:config.MAX_CATEGORIES_ON_CHART-1]
        other_sum = category_expenses.iloc[config.MAX_CATEGORIES_ON_CHART-1:].sum()
        
        # Создаем новую серию с основными категориями и "Прочее"
        new_data = main_categories.copy()
        new_data['прочее'] = other_sum
        category_expenses = new_data
    
    # Создаем диаграмму
    plt.figure(figsize=(10, 8))
    
    # Создаем цветовую палитру
    colors = [config.COLORS.get(cat, "#9E9E9E") for cat in category_expenses.index]
    
    # Добавляем эмодзи к названиям категорий
    categories_with_emoji = [f"{cat} ({config.DEFAULT_CATEGORIES.get(cat, '')})" for cat in category_expenses.index]
    
    bars = plt.barh(categories_with_emoji, category_expenses.values, color=colors)
    
    # Добавляем значения на столбцы
    for bar in bars:
        width = bar.get_width()
        plt.text(width + 5, bar.get_y() + bar.get_height()/2, 
                f'{int(width)}', va='center')
    
    plt.title(f'Распределение расходов по категориям за {year} год')
    plt.xlabel('Сумма')
    plt.ylabel('Категория')
    plt.grid(axis='x', linestyle='--', alpha=0.7)
    
    # Сохраняем диаграмму
    if save_path is None:
        user_dir = excel.create_user_dir(user_id)
        save_path = os.path.join(user_dir, f"category_distribution_{year}.png")
    
    plt.savefig(save_path, bbox_inches='tight')
    plt.close()
    
    return save_path
