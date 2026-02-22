"""
Утилиты для визуализации данных расходов
"""

import os
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib
import matplotlib.ticker as mticker
import matplotlib.patheffects as pe

matplotlib.use('Agg')  # Использование не-интерактивного бэкенда
import seaborn as sns
import datetime
import logging
from utils import excel
import config

logger = logging.getLogger(__name__)

# Русские названия месяцев
MONTH_NAMES_RU = {
    1: 'январь', 2: 'февраль', 3: 'март', 4: 'апрель',
    5: 'май', 6: 'июнь', 7: 'июль', 8: 'август',
    9: 'сентябрь', 10: 'октябрь', 11: 'ноябрь', 12: 'декабрь'
}
MONTH_NAMES_SHORT_RU = {
    1: 'Янв', 2: 'Фев', 3: 'Мар', 4: 'Апр',
    5: 'Май', 6: 'Июн', 7: 'Июл', 8: 'Авг',
    9: 'Сен', 10: 'Окт', 11: 'Ноя', 12: 'Дек'
}

# Цветовая палитра (современная, приглушённая)
PALETTE = [
    "#4E79A7", "#F28E2B", "#E15759", "#76B7B2",
    "#59A14F", "#EDC948", "#B07AA1", "#FF9DA7",
    "#9C755F", "#BAB0AC",
]

# Глобальный стиль
sns.set_theme(style="whitegrid", palette="muted")
plt.rcParams.update({
    'font.family': 'DejaVu Sans',
    'figure.dpi': 150,
    'savefig.dpi': 150,
    'axes.spines.top': False,
    'axes.spines.right': False,
})


def _fmt_amount(value: float) -> str:
    """Форматирует сумму: 1 500 руб."""
    return f"{int(float(value)):,}".replace(",", "\u202f") + "\u00a0руб."


def _cap(name: str) -> str:
    """Первая буква заглавная."""
    return name.capitalize() if name else name


def _get_colors(categories: list) -> list:
    """Возвращает цвета из config или из палитры по умолчанию."""
    result = []
    for i, cat in enumerate(categories):
        color = config.COLORS.get(cat, PALETTE[i % len(PALETTE)])
        result.append(color)
    return result


async def create_monthly_pie_chart(user_id, month=None, year=None, save_path=None, project_id=None):
    """
    Создаёт donut-диаграмму расходов по категориям за указанный месяц.
    """
    if month is None:
        month = datetime.datetime.now().month
    if year is None:
        year = datetime.datetime.now().year

    expenses = await excel.get_month_expenses(user_id, month, year, project_id)

    if not expenses or expenses['total'] == 0:
        return None

    # Сортируем по убыванию
    sorted_categories = sorted(
        expenses['by_category'].items(),
        key=lambda x: x[1],
        reverse=True
    )

    raw_names = []
    amounts = []

    if len(sorted_categories) > config.MAX_CATEGORIES_ON_CHART:
        main_categories = sorted_categories[:config.MAX_CATEGORIES_ON_CHART - 1]
        other_sum = sum(float(item[1]) for item in sorted_categories[config.MAX_CATEGORIES_ON_CHART - 1:])

        for category, amount in main_categories:
            raw_names.append(category)
            amounts.append(float(amount))

        if other_sum > 0:
            raw_names.append("прочее")
            amounts.append(other_sum)
    else:
        for category, amount in sorted_categories:
            raw_names.append(category)
            amounts.append(float(amount))

    total = float(expenses['total'])
    labels = [_cap(n) for n in raw_names]
    colors = _get_colors(raw_names)

    fig, ax = plt.subplots(figsize=(9, 7))
    fig.patch.set_facecolor('white')

    # --- Donut ---
    wedges, _ = ax.pie(
        amounts,
        labels=None,
        startangle=90,
        colors=colors,
        wedgeprops=dict(width=0.52, edgecolor='white', linewidth=2),
        counterclock=False,
    )

    # --- Подписи только для сегментов > 5% ---
    for i, (wedge, amount) in enumerate(zip(wedges, amounts)):
        pct = amount / total * 100
        if pct < 4:
            continue
        angle = (wedge.theta2 + wedge.theta1) / 2
        import math
        x = math.cos(math.radians(angle))
        y = math.sin(math.radians(angle))
        r_mid = 0.72  # внутри кольца
        ax.text(
            x * r_mid, y * r_mid,
            f"{pct:.0f}%",
            ha='center', va='center',
            fontsize=8.5, fontweight='bold', color='white',
        )

    # --- Сумма в центре ---
    ax.text(0, 0.08, "Итого", ha='center', va='center',
            fontsize=10, color='#666666')
    ax.text(0, -0.15, _fmt_amount(total), ha='center', va='center',
            fontsize=13, fontweight='bold', color='#222222')

    # --- Легенда ---
    legend_labels = [
        f"{label}  —  {_fmt_amount(amt)}"
        for label, amt in zip(labels, amounts)
    ]
    ax.legend(
        wedges, legend_labels,
        loc="center left",
        bbox_to_anchor=(1.02, 0.5),
        fontsize=9,
        frameon=False,
        handlelength=1.2,
        handleheight=1.2,
    )

    # --- Заголовок (справа сверху) ---
    month_name = MONTH_NAMES_RU.get(month, str(month))
    ax.set_title(
        f"Расходы за {month_name} {year}",
        loc='right',
        fontsize=12,
        fontweight='bold',
        color='#333333',
        pad=12,
    )

    if save_path is None:
        user_dir = excel.create_user_dir(user_id)
        save_path = os.path.join(user_dir, f"pie_chart_{year}_{month}.png")

    plt.savefig(save_path, bbox_inches='tight', facecolor='white')
    plt.close()

    return save_path


async def create_monthly_bar_chart(user_id, year=None, save_path=None):
    """
    Создаёт столбчатую диаграмму расходов по месяцам за указанный год.
    """
    if year is None:
        year = datetime.datetime.now().year

    expenses_df = await excel.get_all_expenses(user_id, year)

    if expenses_df is None or expenses_df.empty:
        return None

    # Конвертируем Decimal → float
    expenses_df['amount'] = expenses_df['amount'].astype(float)

    monthly_expenses = expenses_df.groupby('month')['amount'].sum()

    months_labels = [MONTH_NAMES_SHORT_RU[i] for i in range(1, 13)]
    amounts = [float(monthly_expenses.get(i, 0)) for i in range(1, 13)]

    max_val = max(amounts) if max(amounts) > 0 else 1
    bar_colors = [
        plt.cm.Blues(0.35 + 0.55 * (v / max_val)) for v in amounts
    ]

    fig, ax = plt.subplots(figsize=(12, 6))
    fig.patch.set_facecolor('white')

    bars = ax.bar(months_labels, amounts, color=bar_colors,
                  edgecolor='white', linewidth=1.5, width=0.65)

    for bar, amount in zip(bars, amounts):
        if amount > 0:
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() + max_val * 0.012,
                _fmt_amount(amount),
                ha='center', va='bottom', fontsize=7.5, fontweight='bold', color='#444444',
            )

    ax.set_title(
        f"Расходы по месяцам за {year} год",
        loc='right',
        fontsize=12, fontweight='bold', color='#333333', pad=12,
    )
    ax.set_xlabel("Месяц", fontsize=10, color='#555555')
    ax.set_ylabel("Сумма, руб.", fontsize=10, color='#555555')
    ax.yaxis.set_major_formatter(
        mticker.FuncFormatter(lambda x, _: f"{int(x):,}".replace(",", "\u202f"))
    )
    ax.set_ylim(0, max_val * 1.18)
    ax.tick_params(colors='#666666')
    sns.despine(left=False, bottom=False)

    if save_path is None:
        user_dir = excel.create_user_dir(user_id)
        save_path = os.path.join(user_dir, f"bar_chart_{year}.png")

    plt.savefig(save_path, bbox_inches='tight', facecolor='white')
    plt.close()

    return save_path


async def create_category_trend_chart(user_id, category, year=None, save_path=None):
    """
    Создаёт линейный график тренда расходов по категории за год.
    """
    if year is None:
        year = datetime.datetime.now().year

    category_data = await excel.get_category_expenses(user_id, category, year)

    if not category_data or category_data['total'] == 0:
        return None

    months_labels = [MONTH_NAMES_SHORT_RU[i] for i in range(1, 13)]
    amounts = [float(category_data['by_month'].get(i, 0)) for i in range(1, 13)]

    line_color = config.COLORS.get(category.lower(), "#4E79A7")

    fig, ax = plt.subplots(figsize=(12, 6))
    fig.patch.set_facecolor('white')

    ax.fill_between(range(12), amounts, alpha=0.12, color=line_color)
    ax.plot(range(12), amounts, marker='o', linestyle='-', color=line_color,
            linewidth=2.5, markersize=8, markerfacecolor='white',
            markeredgewidth=2.5, markeredgecolor=line_color)

    max_val = max(amounts) if max(amounts) > 0 else 1
    for i, amount in enumerate(amounts):
        if amount > 0:
            ax.text(i, amount + max_val * 0.03, _fmt_amount(amount),
                    ha='center', fontsize=8, fontweight='bold', color='#444444')

    ax.set_xticks(range(12))
    ax.set_xticklabels(months_labels)
    ax.set_title(
        f"Расходы на «{_cap(category)}» за {year} год",
        loc='right',
        fontsize=12, fontweight='bold', color='#333333', pad=12,
    )
    ax.set_xlabel("Месяц", fontsize=10, color='#555555')
    ax.set_ylabel("Сумма, руб.", fontsize=10, color='#555555')
    ax.yaxis.set_major_formatter(
        mticker.FuncFormatter(lambda x, _: f"{int(x):,}".replace(",", "\u202f"))
    )
    ax.set_ylim(0, max_val * 1.22)
    ax.tick_params(colors='#666666')
    sns.despine()

    if save_path is None:
        user_dir = excel.create_user_dir(user_id)
        save_path = os.path.join(user_dir, f"trend_{category}_{year}.png")

    plt.savefig(save_path, bbox_inches='tight', facecolor='white')
    plt.close()

    return save_path


async def create_budget_comparison_chart(user_id, year=None, save_path=None):
    """Budget functionality disabled. Returns None."""
    return None


async def create_category_distribution_chart(user_id, year=None, save_path=None):
    """
    Создаёт горизонтальную столбчатую диаграмму распределения расходов по категориям за год.
    """
    if year is None:
        year = datetime.datetime.now().year

    expenses_df = await excel.get_all_expenses(user_id, year)

    if expenses_df is None or expenses_df.empty:
        return None

    # Конвертируем Decimal → float
    expenses_df['amount'] = expenses_df['amount'].astype(float)

    category_expenses = expenses_df.groupby('category')['amount'].sum().sort_values(ascending=True)

    if len(category_expenses) > config.MAX_CATEGORIES_ON_CHART:
        other_sum = float(category_expenses.iloc[:-(config.MAX_CATEGORIES_ON_CHART - 1)].sum())
        category_expenses = category_expenses.iloc[-(config.MAX_CATEGORIES_ON_CHART - 1):]
        category_expenses['прочее'] = other_sum
        category_expenses = category_expenses.sort_values(ascending=True)

    raw_names = list(category_expenses.index)
    amounts_vals = [float(v) for v in category_expenses.values]
    colors = _get_colors(raw_names)
    labels = [_cap(n) for n in raw_names]

    fig, ax = plt.subplots(figsize=(10, max(5, len(category_expenses) * 0.75)))
    fig.patch.set_facecolor('white')

    bars = ax.barh(labels, amounts_vals,
                   color=colors, edgecolor='white', linewidth=1.5, height=0.6)

    max_val = max(amounts_vals) if amounts_vals else 1
    for bar, amount in zip(bars, amounts_vals):
        ax.text(
            bar.get_width() + max_val * 0.01,
            bar.get_y() + bar.get_height() / 2,
            _fmt_amount(amount),
            va='center', fontsize=9, fontweight='bold', color='#444444',
        )

    ax.set_title(
        f"Распределение расходов по категориям за {year} год",
        loc='right',
        fontsize=12, fontweight='bold', color='#333333', pad=12,
    )
    ax.set_xlabel("Сумма, руб.", fontsize=10, color='#555555')
    ax.xaxis.set_major_formatter(
        mticker.FuncFormatter(lambda x, _: f"{int(x):,}".replace(",", "\u202f"))
    )
    ax.set_xlim(0, max_val * 1.22)
    ax.tick_params(colors='#666666')
    sns.despine(left=True, bottom=False)

    if save_path is None:
        user_dir = excel.create_user_dir(user_id)
        save_path = os.path.join(user_dir, f"category_distribution_{year}.png")

    plt.savefig(save_path, bbox_inches='tight', facecolor='white')
    plt.close()

    return save_path
