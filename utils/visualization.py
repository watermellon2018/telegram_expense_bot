"""
Утилиты для визуализации данных расходов
"""

import asyncio
import functools
import math
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
from utils import incomes as income_utils
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


def _tracked(text: str) -> str:
    """Добавляет волосяные пробелы (U+200A) между символами для эффекта letter-spacing ~1-2%."""
    LS = '\u200a'
    result = []
    for i, ch in enumerate(text):
        result.append(ch)
        if i < len(text) - 1 and ch not in (' ', '\n'):
            result.append(LS)
    return ''.join(result)


def _get_colors(categories: list) -> list:
    """Возвращает цвета из config или из палитры по умолчанию."""
    result = []
    for i, cat in enumerate(categories):
        color = config.COLORS.get(cat, PALETTE[i % len(PALETTE)])
        result.append(color)
    return result


# ---------------------------------------------------------------------------
# Синхронные функции рендеринга (выполняются в ThreadPoolExecutor)
# ---------------------------------------------------------------------------

def _render_pie_chart(raw_names: list, amounts: list, total: float,
                      month: int, year: int, save_path: str) -> str:
    """Синхронный рендеринг donut-диаграммы. Вызывается через run_in_executor."""
    labels = [_cap(n) for n in raw_names]
    colors = _get_colors(raw_names)

    fig, ax = plt.subplots(figsize=(10, 6.5))
    fig.patch.set_facecolor('white')
    fig.subplots_adjust(left=0.01, right=0.80, top=0.82, bottom=0.03)

    wedges, _ = ax.pie(
        amounts,
        labels=None,
        startangle=90,
        colors=colors,
        wedgeprops=dict(width=0.50, edgecolor='white', linewidth=0.5),
        counterclock=False,
    )

    scale = 1.3
    ax.set_xlim(-scale, scale)
    ax.set_ylim(-scale, scale)

    THRESHOLD = 5.0
    for i, (wedge, amount) in enumerate(zip(wedges, amounts)):
        pct = amount / total * 100
        category_label = labels[i]
        angle_mid = (wedge.theta1 + wedge.theta2) / 2
        xm = math.cos(math.radians(angle_mid))
        ym = math.sin(math.radians(angle_mid))

        ha_txt = 'left' if xm >= 0 else 'right'
        if pct >= THRESHOLD:
            ax.text(
                xm * 0.74, ym * 0.74,
                f"{pct:.0f}%",
                ha='center', va='center',
                fontsize=8.0, fontweight='bold', color='white',
            )
            x_tip = xm * 1.00
            y_tip = ym * 1.00
            x_txt = xm * 1.09
            y_txt = ym * 1.09
            ax.annotate(
                category_label,
                xy=(x_tip, y_tip),
                xytext=(x_txt, y_txt),
                ha=ha_txt, va='center',
                fontsize=11.0, color=colors[i],
                fontweight='bold',
                annotation_clip=False,
            )
        else:
            x_tip = xm * 1.02
            y_tip = ym * 1.02
            x_txt = xm * 1.10
            y_txt = ym * 1.10
            ax.annotate(
                f"{category_label} {pct:.1f}%",
                xy=(x_tip, y_tip),
                xytext=(x_txt, y_txt),
                ha=ha_txt, va='center',
                fontsize=8.0, color='#555555',
                annotation_clip=False,
                arrowprops=dict(
                    arrowstyle='-',
                    color='#cccccc',
                    lw=1,
                    shrinkA=0, shrinkB=0,
                ),
            )

    ax.text(
        0, 0,
        _fmt_amount(total),
        ha='center', va='center',
        fontsize=16, fontweight=600, color='#2A2A2A',
    )

    sorted_idxs = sorted(range(len(amounts)), key=lambda i: amounts[i], reverse=True)
    legend_handles = [wedges[i] for i in sorted_idxs]

    max_len = max(len(labels[i]) for i in sorted_idxs)
    legend_texts = [
        f"{labels[i].ljust(max_len)}  {_fmt_amount(amounts[i]).rjust(3)}"
        for i in sorted_idxs
    ]
    ax.legend(
        legend_handles, legend_texts,
        loc='center left',
        bbox_to_anchor=(1.06, 0.5),
        fontsize=9,
        frameon=False,
        prop={'family': 'monospace'}
    )

    month_name = MONTH_NAMES_RU.get(month, str(month)).capitalize()
    title_raw = f"Расходы  \u2022  {month_name} {year}"
    fig.text(
        0.55, 0.84,
        _tracked(title_raw),
        ha='center', va='top',
        fontsize=14, fontweight=700, color='#2A2A2A',
    )

    plt.savefig(save_path, bbox_inches='tight', facecolor='white', dpi=150)
    plt.close(fig)
    return save_path


def _render_bar_chart(months_labels: list, amounts: list, year: int,
                      save_path: str) -> str:
    """Синхронный рендеринг столбчатой диаграммы по месяцам."""
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

    plt.savefig(save_path, bbox_inches='tight', facecolor='white')
    plt.close(fig)
    return save_path


def _render_trend_chart(months_labels: list, amounts: list, category: str,
                        line_color: str, year: int, save_path: str) -> str:
    """Синхронный рендеринг линейного графика тренда по категории."""
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

    plt.savefig(save_path, bbox_inches='tight', facecolor='white')
    plt.close(fig)
    return save_path


def _render_distribution_chart(raw_names: list, amounts_vals: list,
                                year: int, save_path: str) -> str:
    """Синхронный рендеринг горизонтальной столбчатой диаграммы распределения."""
    colors = _get_colors(raw_names)
    labels = [_cap(n) for n in raw_names]

    fig, ax = plt.subplots(figsize=(10, max(5, len(raw_names) * 0.75)))
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

    plt.savefig(save_path, bbox_inches='tight', facecolor='white')
    plt.close(fig)
    return save_path


# ---------------------------------------------------------------------------
# Публичные async-функции: получают данные из БД, затем рендерят в потоке
# ---------------------------------------------------------------------------

async def create_monthly_pie_chart(user_id, month=None, year=None, save_path=None, project_id=None):
    """
    Создаёт donut-диаграмму расходов по категориям за указанный месяц.
    Рендеринг matplotlib выполняется в ThreadPoolExecutor, не блокируя event loop.
    """
    if month is None:
        month = datetime.datetime.now().month
    if year is None:
        year = datetime.datetime.now().year

    expenses = await excel.get_month_expenses(user_id, month, year, project_id)

    if not expenses or expenses['total'] == 0:
        return None

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

    total = sum(amounts)

    if save_path is None:
        user_dir = excel.create_user_dir(user_id)
        save_path = os.path.join(user_dir, f"pie_chart_{year}_{month}.png")

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None,
        functools.partial(_render_pie_chart, raw_names, amounts, total, month, year, save_path)
    )


async def create_category_trend_chart(user_id, category, year=None, save_path=None):
    """
    Создаёт линейный график тренда расходов по категории за год.
    Рендеринг matplotlib выполняется в ThreadPoolExecutor, не блокируя event loop.
    """
    if year is None:
        year = datetime.datetime.now().year

    category_data = await excel.get_category_expenses(user_id, category, year)

    if not category_data or category_data['total'] == 0:
        return None

    months_labels = [MONTH_NAMES_SHORT_RU[i] for i in range(1, 13)]
    amounts = [float(category_data['by_month'].get(i, 0)) for i in range(1, 13)]
    line_color = config.COLORS.get(category.lower(), "#4E79A7")

    if save_path is None:
        user_dir = excel.create_user_dir(user_id)
        save_path = os.path.join(user_dir, f"trend_{category}_{year}.png")

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None,
        functools.partial(_render_trend_chart, months_labels, amounts, category, line_color, year, save_path)
    )


def _render_budget_comparison_chart(budget_by_month: dict, spending_by_month: dict,
                                     year: int, save_path: str) -> str:
    """Синхронный рендеринг диаграммы «Бюджет vs. расходы по месяцам»."""
    from matplotlib.patches import Patch
    from matplotlib.lines import Line2D

    months_labels = [MONTH_NAMES_SHORT_RU[i] for i in range(1, 13)]
    spendings = [spending_by_month.get(i, 0.0) for i in range(1, 13)]
    budgets_line = [budget_by_month.get(i) for i in range(1, 13)]  # None где бюджет не задан

    # Цвет столбца: зелёный — в рамках бюджета, красный — перерасход, голубой — нет бюджета
    colors = []
    for i in range(12):
        b = budgets_line[i]
        if b is None:
            colors.append('#90CAF9')   # голубой — бюджет не задан
        elif spendings[i] <= b:
            colors.append('#66BB6A')   # зелёный — ОК
        else:
            colors.append('#EF5350')   # красный — перерасход

    max_spending = max(spendings) if any(s > 0 for s in spendings) else 0
    max_budget = max((b for b in budgets_line if b is not None), default=0)
    max_val = max(max_spending, max_budget, 1)

    fig, ax = plt.subplots(figsize=(12, 6))
    fig.patch.set_facecolor('white')

    bars = ax.bar(months_labels, spendings, color=colors,
                  edgecolor='white', linewidth=1.5, width=0.65)

    # Подписи значений над столбцами
    for bar, amount in zip(bars, spendings):
        if amount > 0:
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() + max_val * 0.012,
                _fmt_amount(amount),
                ha='center', va='bottom', fontsize=7.5, fontweight='bold', color='#444444',
            )

    # Горизонтальные пунктирные отрезки бюджета для каждого месяца
    for i, b in enumerate(budgets_line):
        if b is not None:
            ax.plot(
                [i - 0.38, i + 0.38], [b, b],
                color='#FF6F00', linewidth=2.0, linestyle='--', alpha=0.85,
                solid_capstyle='round',
            )

    ax.set_title(
        f"Бюджет vs. расходы  •  {year} год",
        loc='right',
        fontsize=12, fontweight='bold', color='#333333', pad=12,
    )
    ax.set_xlabel("Месяц", fontsize=10, color='#555555')
    ax.set_ylabel("Сумма, руб.", fontsize=10, color='#555555')
    ax.yaxis.set_major_formatter(
        mticker.FuncFormatter(lambda x, _: f"{int(x):,}".replace(",", "\u202f"))
    )
    ax.set_ylim(0, max_val * 1.25)
    ax.tick_params(colors='#666666')

    legend_elements = [
        Patch(facecolor='#66BB6A', label='В рамках бюджета'),
        Patch(facecolor='#EF5350', label='Превышение бюджета'),
        Patch(facecolor='#90CAF9', label='Бюджет не задан'),
        Line2D([0], [0], color='#FF6F00', linewidth=2.0, linestyle='--', label='Лимит бюджета'),
    ]
    ax.legend(handles=legend_elements, loc='upper left', frameon=False, fontsize=9)

    sns.despine(left=False, bottom=False)
    plt.savefig(save_path, bbox_inches='tight', facecolor='white')
    plt.close(fig)
    return save_path


async def create_budget_comparison_chart(user_id, year=None, save_path=None, project_id=None):
    """
    Создаёт столбчатую диаграмму «Бюджет vs. расходы по месяцам».
    Зелёные столбцы — расходы в рамках бюджета, красные — превышение.
    Пунктирные горизонтальные линии — установленный лимит бюджета.
    Рендеринг выполняется в ThreadPoolExecutor, не блокируя event loop.
    """
    if year is None:
        year = datetime.datetime.now().year

    from utils import budgets as budgets_utils
    budgets_list = await budgets_utils.get_budgets_for_year(user_id, year, project_id)
    if not budgets_list:
        return None

    budget_by_month = {b['month']: b['amount'] for b in budgets_list}

    # Получаем фактические расходы
    expenses_df = await excel.get_all_expenses(user_id, year)
    spending_by_month: dict = {}
    if expenses_df is not None and not expenses_df.empty:
        expenses_df['amount'] = expenses_df['amount'].astype(float)
        monthly = expenses_df.groupby('month')['amount'].sum()
        spending_by_month = {int(m): float(v) for m, v in monthly.items()}

    if save_path is None:
        user_dir = excel.create_user_dir(user_id)
        save_path = os.path.join(user_dir, f"budget_comparison_{year}.png")

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None,
        functools.partial(
            _render_budget_comparison_chart,
            budget_by_month, spending_by_month, year, save_path,
        )
    )


async def create_category_distribution_chart(user_id, year=None, save_path=None):
    """
    Создаёт горизонтальную столбчатую диаграмму распределения расходов по категориям за год.
    Рендеринг matplotlib выполняется в ThreadPoolExecutor, не блокируя event loop.
    """
    if year is None:
        year = datetime.datetime.now().year

    expenses_df = await excel.get_all_expenses(user_id, year)

    if expenses_df is None or expenses_df.empty:
        return None

    expenses_df['amount'] = expenses_df['amount'].astype(float)
    category_expenses = expenses_df.groupby('category')['amount'].sum().sort_values(ascending=True)

    if len(category_expenses) > config.MAX_CATEGORIES_ON_CHART:
        other_sum = float(category_expenses.iloc[:-(config.MAX_CATEGORIES_ON_CHART - 1)].sum())
        category_expenses = category_expenses.iloc[-(config.MAX_CATEGORIES_ON_CHART - 1):]
        category_expenses['прочее'] = other_sum
        category_expenses = category_expenses.sort_values(ascending=True)

    raw_names = list(category_expenses.index)
    amounts_vals = [float(v) for v in category_expenses.values]

    if save_path is None:
        user_dir = excel.create_user_dir(user_id)
        save_path = os.path.join(user_dir, f"category_distribution_{year}.png")

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None,
        functools.partial(_render_distribution_chart, raw_names, amounts_vals, year, save_path)
    )


def _render_income_vs_expense_chart(months_labels: list, income_amounts: list, expense_amounts: list, year: int, save_path: str) -> str:
    """Синхронный рендер сравнительного графика доходов и расходов по месяцам."""
    fig, ax = plt.subplots(figsize=(12, 6))
    fig.patch.set_facecolor("white")

    x = list(range(len(months_labels)))
    width = 0.36

    income_bars = ax.bar(
        [v - width / 2 for v in x],
        income_amounts,
        width=width,
        color="#4CAF50",
        edgecolor="white",
        linewidth=1.2,
        label="Доходы",
    )
    expense_bars = ax.bar(
        [v + width / 2 for v in x],
        expense_amounts,
        width=width,
        color="#E15759",
        edgecolor="white",
        linewidth=1.2,
        label="Расходы",
    )

    max_val = max(max(income_amounts, default=0), max(expense_amounts, default=0), 1)
    for bar in income_bars:
        if bar.get_height() > 0:
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() + max_val * 0.01,
                _fmt_amount(bar.get_height()),
                ha="center",
                va="bottom",
                fontsize=7,
                color="#2F6F36",
            )
    for bar in expense_bars:
        if bar.get_height() > 0:
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() + max_val * 0.01,
                _fmt_amount(bar.get_height()),
                ha="center",
                va="bottom",
                fontsize=7,
                color="#8B2C2A",
            )

    ax.set_xticks(x)
    ax.set_xticklabels(months_labels)
    ax.set_title(
        f"Доходы vs. расходы по месяцам за {year} год",
        loc="right",
        fontsize=12,
        fontweight="bold",
        color="#333333",
    )
    ax.set_xlabel("Месяц", fontsize=10, color="#555555")
    ax.set_ylabel("Сумма, руб.", fontsize=10, color="#555555")
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda val, _: f"{int(val):,}".replace(",", "\u202f")))
    ax.set_ylim(0, max_val * 1.2)
    ax.legend(frameon=False)
    sns.despine(left=False, bottom=False)

    plt.savefig(save_path, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return save_path


async def create_income_distribution_chart(user_id, year=None, save_path=None, project_id=None):
    """Создаёт диаграмму распределения доходов по категориям за год."""
    if year is None:
        year = datetime.datetime.now().year

    incomes_df = await income_utils.get_all_incomes(user_id, year, project_id)
    if incomes_df is None or incomes_df.empty:
        return None

    incomes_df["amount"] = incomes_df["amount"].astype(float)
    category_incomes = incomes_df.groupby("category")["amount"].sum().sort_values(ascending=True)

    top_n = 5
    if len(category_incomes) > top_n:
        other_sum = float(category_incomes.iloc[:-(top_n - 1)].sum())
        category_incomes = category_incomes.iloc[-(top_n - 1):]
        category_incomes["прочее"] = other_sum
        category_incomes = category_incomes.sort_values(ascending=True)

    raw_names = list(category_incomes.index)
    amounts_vals = [float(v) for v in category_incomes.values]

    if save_path is None:
        user_dir = excel.create_user_dir(user_id)
        save_path = os.path.join(user_dir, f"income_distribution_{year}.png")

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None,
        functools.partial(_render_distribution_chart, raw_names, amounts_vals, year, save_path),
    )


async def create_income_vs_expense_chart(user_id, year=None, save_path=None, project_id=None):
    """Создаёт сравнительный график «доходы vs расходы» по месяцам."""
    if year is None:
        year = datetime.datetime.now().year

    comparison = await income_utils.get_yearly_income_vs_expense(user_id, year, project_id)
    incomes_by_month = comparison.get("incomes", {})
    expenses_by_month = comparison.get("expenses", {})
    if not incomes_by_month and not expenses_by_month:
        return None

    months_labels = [MONTH_NAMES_SHORT_RU[i] for i in range(1, 13)]
    income_amounts = [float(incomes_by_month.get(i, 0.0)) for i in range(1, 13)]
    expense_amounts = [float(expenses_by_month.get(i, 0.0)) for i in range(1, 13)]

    if save_path is None:
        user_dir = excel.create_user_dir(user_id)
        save_path = os.path.join(user_dir, f"income_vs_expense_{year}.png")

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None,
        functools.partial(_render_income_vs_expense_chart, months_labels, income_amounts, expense_amounts, year, save_path),
    )
