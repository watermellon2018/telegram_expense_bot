"""
Генератор PDF-отчётов по расходам пользователя.
Создаёт многостраничный PDF с графиками, таблицами и аналитикой
за скользящие 12 месяцев (от текущей даты).
"""

import asyncio
import functools
import os
import datetime
import logging
from typing import Optional

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import matplotlib.patches as mpatches
import matplotlib.gridspec as gridspec
from matplotlib.backends.backend_pdf import PdfPages
import seaborn as sns

from utils import excel
from utils import incomes as income_utils
import config

logger = logging.getLogger(__name__)

# ─── Русские названия ───────────────────────────────────────────────────────
MONTH_NAMES_RU = {
    1: 'Январь', 2: 'Февраль', 3: 'Март', 4: 'Апрель',
    5: 'Май', 6: 'Июнь', 7: 'Июль', 8: 'Август',
    9: 'Сентябрь', 10: 'Октябрь', 11: 'Ноябрь', 12: 'Декабрь',
}
MONTH_SHORT_RU = {
    1: 'Янв', 2: 'Фев', 3: 'Мар', 4: 'Апр',
    5: 'Май', 6: 'Июн', 7: 'Июл', 8: 'Авг',
    9: 'Сен', 10: 'Окт', 11: 'Ноя', 12: 'Дек',
}
WEEKDAY_SHORT_RU = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']

PALETTE = [
    "#4E79A7", "#F28E2B", "#E15759", "#76B7B2",
    "#59A14F", "#EDC948", "#B07AA1", "#FF9DA7",
    "#9C755F", "#BAB0AC", "#86BCB6", "#D4A6C8",
]

# ─── Вспомогательные функции ────────────────────────────────────────────────

def _fmt(value: float) -> str:
    """Форматирует сумму: 1 234 567 ₽"""
    return f"{int(round(float(value))):,}".replace(",", "\u202f") + "\u00a0₽"


def _get_cat_color(cat: str, idx: int = 0) -> str:
    return config.COLORS.get(str(cat).lower(), PALETTE[idx % len(PALETTE)])


def _cap(s: str) -> str:
    return s.capitalize() if s else s


def _set_style():
    sns.set_theme(style="whitegrid", palette="muted")
    plt.rcParams.update({
        'font.family': 'DejaVu Sans',
        'figure.dpi': 120,
        'savefig.dpi': 120,
        'axes.spines.top': False,
        'axes.spines.right': False,
        'xtick.labelsize': 12,
        'ytick.labelsize': 12,
    })


def _rub_formatter(x, _):
    return f"{int(x):,}".replace(",", "\u202f")


# ─── Строит скользящее окно 12 месяцев ──────────────────────────────────────

def _rolling_months(today: datetime.date) -> list:
    """Возвращает список (year, month) за последние 12 месяцев включительно."""
    months = []
    for i in range(11, -1, -1):
        # Сдвиг назад на i месяцев
        m = today.month - i
        y = today.year
        while m <= 0:
            m += 12
            y -= 1
        months.append((y, m))
    return months


def _month_label(year: int, month: int, today: datetime.date) -> str:
    """Подпись месяца: «Янв» или «Янв'25» если год не текущий."""
    short = MONTH_SHORT_RU[month]
    if year != today.year:
        return f"{short} {str(year)[2:]}"
    return short


# ─── Страница 1: Обзор — KPI + line + топ-5 + pivot ─────────────────────────

def _page_overview(pdf: PdfPages, df: pd.DataFrame, today: datetime.date):
    months = _rolling_months(today)
    cur_year, cur_month = today.year, today.month
    prev_month = today.month - 1 if today.month > 1 else 12
    prev_year = today.year if today.month > 1 else today.year - 1

    total = df['amount'].sum()
    cur_month_df = df[(df['date'].dt.month == cur_month) & (df['date'].dt.year == cur_year)]
    prev_month_df = df[(df['date'].dt.month == prev_month) & (df['date'].dt.year == prev_year)]
    cur_total = cur_month_df['amount'].sum()
    prev_total = prev_month_df['amount'].sum()
    diff_pct = ((cur_total - prev_total) / prev_total * 100) if prev_total else 0

    # Суммы по скользящим месяцам
    monthly_totals = []
    for y, m in months:
        s = df[(df['date'].dt.year == y) & (df['date'].dt.month == m)]['amount'].sum()
        monthly_totals.append(float(s))

    month_labels = [_month_label(y, m, today) for y, m in months]

    # Топ-5 категорий
    cat_totals = df.groupby('category')['amount'].sum().sort_values(ascending=False)
    top5 = cat_totals.head(5)

    # Самая дорогая покупка в каждой из топ-5
    top5_expensive = {}
    for cat in top5.index:
        sub = df[df['category'] == cat].nlargest(1, 'amount')
        if not sub.empty:
            row = sub.iloc[0]
            desc = str(row['description']) if pd.notna(row.get('description', None)) and row['description'] else ''
            top5_expensive[cat] = (float(row['amount']), row['date'].strftime('%d.%m.%Y'), desc)

    # Pivot: средний чек (сумма/кол-во) по месяцу × категории
    top_cats = list(cat_totals.head(min(8, len(cat_totals))).index)
    pivot_rows = []
    for y, m in months:
        sub = df[(df['date'].dt.year == y) & (df['date'].dt.month == m)]
        row_data = {'Месяц': f"{MONTH_SHORT_RU[m]} {str(y)[2:]}"}
        for cat in top_cats:
            cat_sub = sub[sub['category'] == cat]
            if not cat_sub.empty and len(cat_sub) > 0:
                avg = cat_sub['amount'].sum() / len(cat_sub)
                row_data[_cap(cat)] = f"{int(round(avg)):,}".replace(",", "\u202f")
            else:
                row_data[_cap(cat)] = '—'
        pivot_rows.append(row_data)

    fig = plt.figure(figsize=(22, 22))
    fig.patch.set_facecolor('white')
    _set_style()

    # ── KPI-блоки ────────────────────────────────────────────────────────────
    kpi_ax = fig.add_axes([0.09, 0.83, 0.95, 0.10])
    kpi_ax.set_axis_off()

    kpi_items = [
        (f"Прошлый месяц\n({MONTH_NAMES_RU[prev_month]})", _fmt(prev_total), "#F28E2B"),
        (f"Текущий месяц\n({MONTH_NAMES_RU[cur_month]})", _fmt(cur_total), "#59A14F"),
        ("Сравнение с прошлым месяцем\n(в процентах)",
         (f"+{diff_pct:.1f}%" if diff_pct >= 0 else f"{diff_pct:.1f}%"),
         "#E15759" if diff_pct > 0 else "#59A14F"),
         ("Итого за год", _fmt(total), "#4E79A7"),
    ]
    for i, (label, value, color) in enumerate(kpi_items):
        x0 = i * 0.25 + 0.01
        rect = mpatches.FancyBboxPatch(
            (x0, 0.05), 0.2, 0.85,
            boxstyle="round,pad=0.02",
            facecolor=color, alpha=0.2,
            transform=kpi_ax.transAxes, clip_on=False,
        )
        kpi_ax.add_patch(rect)
        kpi_ax.text(x0 + 0.1, 0.72, label, ha='center', va='top',
                    fontsize=20, color='#555555', transform=kpi_ax.transAxes)
        kpi_ax.text(x0 + 0.1, 0.3, value, ha='center', va='center',
                    fontsize=25, fontweight='bold', color=color,
                    transform=kpi_ax.transAxes)

    fig.suptitle(f"Отчёт по расходам  •  {MONTH_NAMES_RU[cur_month]} {cur_year}",
             fontsize=25, fontweight='bold', color='#2A2A2A', y=0.95, x=0.545, ha="center")


    # ── Line-график ──────────────────────────────────────────────────────────
    ax_line = fig.add_subplot(4, 1, 2)
    ax_line.set_position([0.09, 0.63, 0.92, 0.17])
    
    max_v = max(monthly_totals) if monthly_totals else 1
    ax_line.fill_between(range(12), monthly_totals, alpha=0.10, color="#4E79A7")
    ax_line.plot(range(12), monthly_totals, marker='o', color="#4E79A7",
                 linewidth=2.5, markersize=7, markerfacecolor='white',
                 markeredgewidth=2.5, markeredgecolor="#4E79A7")
    for i, v in enumerate(monthly_totals):
        if v > 0:
            ax_line.text(i, v + max_v * 0.04, _fmt(v),
                         ha='center', fontsize=12, fontweight='bold', color='#444444')
    ax_line.set_xticks(range(12))
    ax_line.set_xticklabels(month_labels, fontsize=12)
    ax_line.yaxis.set_major_formatter(mticker.FuncFormatter(_rub_formatter))
    ax_line.set_ylim(0, max_v * 1.25)
    ax_line.set_title("Расходы по месяцам (скользящий год)",
                      fontsize=20, fontweight='bold', color='#333333', loc='left', pad=10)
    ax_line.tick_params(colors='#666666', labelsize=12)
    sns.despine(ax=ax_line)

    # ── Топ-5 категорий ──────────────────────────────────────────────────────
    ax_top = fig.add_axes([0.09, 0.43, 0.44, 0.16])
    ax_top.set_axis_off()
    ax_top.set_title("Топ-5 категорий за год", fontsize=20, fontweight='bold',
                     color='#333333', loc='left', pad=3)

    col_labels = ['Категория', 'Сумма', '%', 'Самая дорогая покупка']
    table_data = []
    for i, (cat, s) in enumerate(top5.items()):
        pct = s / total * 100 if total else 0
        exp = top5_expensive.get(cat, (0, '', ''))
        exp_str = f"{_fmt(exp[0])} ({exp[1]})"
        if exp[2]:
            exp_str += f"\n({exp[2][:30]})"
        table_data.append([_cap(cat), _fmt(s), f"{pct:.1f}%", exp_str])

    # Make a more compact table with larger font, less padding, and optimized bbox
    tbl = ax_top.table(
        cellText=table_data,
        colLabels=col_labels,
        cellLoc='center',
        loc='upper left',
        bbox=[0, 0, 0.93, 0.95]
    )
    tbl.auto_set_font_size(False)
    tbl.set_fontsize(18)  # larger font

    # Set column widths manually
    col_widths = [0.23, 0.21, 0.13, 0.42]  # сумма ≈ 1.0
    for i, w in enumerate(col_widths):
        for row in range(len(table_data) + 1):  # +1 для заголовка
            tbl[(row, i)].set_width(w)

    for (r, c), cell in tbl.get_celld().items():
        cell.get_text().set_wrap(True)
        cell.set_edgecolor('#dddddd')
        cell.set_linewidth(0.6)
        cell.PAD = 0.08
        if r == 0:
            cell.set_facecolor('#4E79A7')
            cell.set_text_props(color='white', fontweight='bold')
        elif r % 2 == 0:
            cell.set_facecolor('#f2f4f8')
        else:
            cell.set_facecolor('white')
        # Make columns a little more compact
        cell.set_fontsize(18)
    
    
    base_height = 0.12  # базовая высота строки
    for r in range(1, len(table_data) + 1):
        text = table_data[r-1][3]  # последний столбец
        lines = text.count("\n") + 1

        row_height = base_height * lines

        for c in range(len(col_labels)):
            tbl[(r, c)].set_height(row_height)

    # Высота заголовка таблицы
    header_height = 0.16
    for c in range(len(col_labels)):
        tbl[(0, c)].set_height(header_height)
    # Remove automatic column width for more compactness, manually set width if needed
    # tbl.auto_set_column_width([0, 1, 2, 3])  # not used for compactness

    # ── Три виджета (справа от топ-5) ────────────────────────────────────────
    widget_ax = fig.add_axes([0.53, 0.44, 0.51, 0.16])
    widget_ax.set_axis_off()

    n_tx = len(df)
    avg_monthly = float(total / 12) if total else 0.0
    avg_check = float(df['amount'].mean()) if n_tx > 0 else 0.0

    widget_items = [
        ("Транзакций", f"{n_tx:,}".replace(",", "\u202f"), "#4E79A7"),
        ("Средний расход\nв месяц", _fmt(avg_monthly), "#59A14F"),
        ("Средний чек", _fmt(avg_check), "#F28E2B"),
    ]

    for i, (label, value, color) in enumerate(widget_items):
        x0 = i * 0.334
        rect = mpatches.FancyBboxPatch(
            (x0 + 0.01, 0.06), 0.27, 0.68,
            boxstyle="round,pad=0.02",
            facecolor=color, alpha=0.15,
            transform=widget_ax.transAxes, clip_on=False,
        )
        widget_ax.add_patch(rect)
        widget_ax.text(x0 + 0.15, 0.5, label, ha='center', va='top',
                       fontsize=20, color='#555555',
                       transform=widget_ax.transAxes, multialignment='center')
        widget_ax.text(x0 + 0.15, 0.25, value, ha='center', va='center',
                       fontsize=25, fontweight='bold', color=color,
                       transform=widget_ax.transAxes)

    # ── Средний чек по категориям (pivot) ────────────────────────────────────
    fig.text(0.09, 0.40, "Средний чек по категориям, ₽",
             fontsize=20, fontweight='bold', color='#333333')

    ax_pivot = fig.add_axes([0.09, 0.05, 0.93, 0.34])
    ax_pivot.set_axis_off()

    pivot_cols = ['Месяц'] + [_cap(c) for c in top_cats]
    pivot_vals = [[row.get(col, '—') for col in pivot_cols] for row in pivot_rows]

    n_cats = len(top_cats)
    month_col_w = 0.10
    cat_col_w = round((1.0 - month_col_w) / n_cats, 4) if n_cats else 0.11

    tbl_piv = ax_pivot.table(
        cellText=pivot_vals,
        colLabels=pivot_cols,
        cellLoc='center',
        loc='center',
        bbox=[0, 0, 1, 1],
    )
    tbl_piv.auto_set_font_size(False)
    tbl_piv.set_fontsize(18)

    for row_i in range(len(pivot_vals) + 1):
        tbl_piv[(row_i, 0)].set_width(month_col_w)
        for col_i in range(1, n_cats + 1):
            tbl_piv[(row_i, col_i)].set_width(cat_col_w)

    for (r, c), cell in tbl_piv.get_celld().items():
        cell.set_edgecolor('#dddddd')
        cell.set_linewidth(0.6)
        cell.PAD = 0.06
        cell.set_fontsize(18)
        if r == 0:
            cell.set_facecolor('#4E79A7')
            cell.set_text_props(color='white', fontweight='bold')
        elif c == 0:
            cell.set_facecolor('#e8eef4')
            cell.set_text_props(fontweight='bold')
        elif r % 2 == 0:
            cell.set_facecolor('#f5f7fa')
        else:
            cell.set_facecolor('white')

    pdf.savefig(fig, bbox_inches='tight', pad_inches=0.5, facecolor='white')
    plt.close(fig)


# ─── Страница 2: Структура — большая сводная таблица по месяцам ─────────────

def _page_structure_table(pdf: PdfPages, df: pd.DataFrame, today: datetime.date):
    months = _rolling_months(today)
    cur_m, cur_y = today.month, today.year
    prev_m = cur_m - 1 if cur_m > 1 else 12
    prev_y = cur_y if cur_m > 1 else cur_y - 1
    six_ago_m = cur_m - 6 if cur_m > 6 else cur_m - 6 + 12
    six_ago_y = cur_y if cur_m > 6 else cur_y - 1
    monthly_sums = {(y, m): df[(df['date'].dt.year == y) & (df['date'].dt.month == m)]['amount'].sum()
                    for y, m in months}
    non_zero = {k: v for k, v in monthly_sums.items() if v > 0}
    richest = max(non_zero, key=non_zero.get) if non_zero else months[-1]

    fig = plt.figure(figsize=(22, 22))
    fig.patch.set_facecolor('white')
    _set_style()
    fig.suptitle("Раздел 2 — Структура расходов",
                 fontsize=25, fontweight='bold', color='#2A2A2A', y=0.95)

    ax = fig.add_axes([0.17, 0.575, 0.78, 0.34])
    ax.set_axis_off()

    col_labels = [f"{MONTH_SHORT_RU[m]} {str(y)[2:]}" for y, m in months]
    row_labels = [
        'Факт (₽)',
        'Бюджет (₽)',
        'Разница (₽)',
        'Разница (%)',
        '% бюджета',
        'Топ-категория',
        'Ср. расход/день',
        'День макс. трат',
        'Самая дорогая\nпокупка (₽+кат.)',
    ]

    table_data = [[] for _ in row_labels]
    for y, m in months:
        sub = df[(df['date'].dt.year == y) & (df['date'].dt.month == m)]
        fact = sub['amount'].sum()
        table_data[0].append(_fmt(fact) if fact else '—')
        table_data[1].append('Н/Д')
        table_data[2].append('Н/Д')
        table_data[3].append('Н/Д')
        table_data[4].append('Н/Д')

        if not sub.empty:
            top_cat = sub.groupby('category')['amount'].sum().idxmax()
            table_data[5].append(_cap(top_cat))

            # Кол-во дней в месяце
            import calendar
            days_in_month = calendar.monthrange(y, m)[1]
            # Если это текущий месяц — делим на прошедшие дни
            if y == today.year and m == today.month:
                days_elapsed = max(today.day, 1)
            else:
                days_elapsed = days_in_month
            avg_day = fact / days_elapsed if days_elapsed else 0
            table_data[6].append(_fmt(avg_day))

            # День с максимальными тратами
            day_totals = sub.groupby(sub['date'].dt.day)['amount'].sum()
            max_day = int(day_totals.idxmax())
            table_data[7].append(f"{max_day:02d}.{m:02d}.{y}")

            # Самая дорогая покупка
            top_row = sub.nlargest(1, 'amount').iloc[0]
            desc = str(top_row['description']) if pd.notna(top_row.get('description', None)) and top_row['description'] else ''
            purchase_str = f"{_fmt(float(top_row['amount']))}\n{_cap(top_row['category'])}"
            if desc:
                purchase_str += f"\n{desc[:20]}"
            table_data[8].append(purchase_str)
        else:
            for ri in [5, 6, 7, 8]:
                table_data[ri].append('—')

    tbl = ax.table(
        cellText=table_data,
        rowLabels=row_labels,
        colLabels=col_labels,
        cellLoc='center',
        rowLoc='center',
        loc='center',
        bbox=[0, 0, 1, 1],
    )
    tbl.auto_set_font_size(False)
    tbl.set_fontsize(18)

    for (r, c), cell in tbl.get_celld().items():
        cell.set_edgecolor('#dddddd')
        cell.set_fontsize(18)
        if r == 0:
            cell.set_facecolor('#4E79A7')
            cell.set_text_props(color='white', fontweight='bold', fontsize=18)
        elif c == -1:
            cell.set_facecolor('#e8eef4')
            cell.set_text_props(fontweight='bold', fontsize=18)
        elif r % 2 == 0:
            cell.set_facecolor('#f5f7fa')
        else:
            cell.set_facecolor('white')

    # ── Круговые диаграммы: все 4 в один ряд ─────────────────────────────────
    ry, rm = richest
    fig.text(0.5, 0.54, "Круговые диаграммы",
             ha='center', fontsize=23, fontweight='bold', color='#333333')

    pie_w, pie_h, pie_y = 0.21, 0.36, 0.14
    pie_title_y = pie_y + pie_h + 0.008   # фиксированная y для всех заголовков
    pie_xs = [0.04, 0.28, 0.52, 0.76]
    pie_titles = [
        f"Текущий — {MONTH_NAMES_RU[cur_m]} {cur_y}",
        f"Прошлый — {MONTH_NAMES_RU[prev_m]} {prev_y}",
        f"6 мес. назад — {MONTH_NAMES_RU[six_ago_m]} {six_ago_y}",
        f"Самый дорогой — {MONTH_NAMES_RU[rm]} {ry}",
    ]
    for px, ptitle in zip(pie_xs, pie_titles):
        fig.text(px + pie_w / 2, pie_title_y, ptitle,
                 ha='center', va='bottom', fontsize=16, fontweight='bold', color='#333333')

    ax_pie1 = fig.add_axes([pie_xs[0], pie_y, pie_w, pie_h])
    ax_pie2 = fig.add_axes([pie_xs[1], pie_y, pie_w, pie_h])
    ax_pie3 = fig.add_axes([pie_xs[2], pie_y, pie_w, pie_h])
    ax_pie4 = fig.add_axes([pie_xs[3], pie_y, pie_w, pie_h])
    _pie_for_period(ax_pie1, df, cur_y,     cur_m,     "")
    _pie_for_period(ax_pie2, df, prev_y,    prev_m,    "")
    _pie_for_period(ax_pie3, df, six_ago_y, six_ago_m, "")
    _pie_for_period(ax_pie4, df, ry,        rm,        "")

    pdf.savefig(fig, bbox_inches='tight', pad_inches=0.5, facecolor='white')
    plt.close(fig)


# ─── Страница 3: 4 круговых диаграммы ───────────────────────────────────────

def _pie_for_period(ax, df: pd.DataFrame, year: int, month: int, title: str):
    sub = df[(df['date'].dt.year == year) & (df['date'].dt.month == month)]
    if sub.empty:
        ax.text(0.5, 0.5, 'Нет данных', ha='center', va='center',
                fontsize=16, fontweight='bold', color='#999999', transform=ax.transAxes)
        if title:
            ax.set_title(title, fontsize=20, fontweight='bold', color='#333333', pad=6)
        ax.axis('off')
        return

    cat_sums = sub.groupby('category')['amount'].sum().sort_values(ascending=False)
    MAX_CATS = 7
    if len(cat_sums) > MAX_CATS:
        main = cat_sums.head(MAX_CATS - 1)
        other = cat_sums.iloc[MAX_CATS - 1:].sum()
        cat_sums = pd.concat([main, pd.Series({'прочее': other})])

    labels = [_cap(c) for c in cat_sums.index]
    values = cat_sums.values.astype(float)
    colors = [_get_cat_color(c, i) for i, c in enumerate(cat_sums.index)]
    total = values.sum()

    wedges, _ = ax.pie(values, labels=None, colors=colors,
                       startangle=90, counterclock=False,
                       wedgeprops=dict(width=0.5, edgecolor='white', linewidth=0.5))
    ax.text(0, 0, _fmt(total), ha='center', va='center',
            fontsize=15, fontweight='bold', color='#2A2A2A')

    legend_texts = [f"{lbl}  {v/total*100:.0f}%" for lbl, v in zip(labels, values)]
    ax.legend(wedges, legend_texts, loc='lower center', bbox_to_anchor=(0.5, -0.17),
              fontsize=14, frameon=False, ncol=2)
    if title:
        ax.set_title(title, fontsize=20, fontweight='bold', color='#333333', pad=6)


# ─── Страница 4: Bar-сравнение + Stacked bar ─────────────────────────────────

def _page_bar_charts(pdf: PdfPages, df: pd.DataFrame, today: datetime.date):
    months = _rolling_months(today)
    month_labels = [_month_label(y, m, today) for y, m in months]
    monthly_totals = [float(df[(df['date'].dt.year == y) & (df['date'].dt.month == m)]['amount'].sum())
                      for y, m in months]

    # Топ категорий для stacked bar и line chart
    top_cats = df.groupby('category')['amount'].sum().sort_values(ascending=False)
    top_cats_list = list(top_cats.head(min(10, len(top_cats))).index)

    stacked = {}
    for cat in top_cats_list:
        stacked[cat] = [
            float(df[(df['date'].dt.year == y) & (df['date'].dt.month == m) &
                     (df['category'] == cat)]['amount'].sum())
            for y, m in months
        ]

    fig = plt.figure(figsize=(26, 20))
    fig.patch.set_facecolor('white')
    _set_style()
    fig.suptitle("Раздел 2 — Структура расходов",
                 fontsize=25, fontweight='bold', color='#2A2A2A', y=0.95)

    gs = gridspec.GridSpec(2, 2, figure=fig, height_ratios=[1, 1], hspace=0.40)
    ax1 = fig.add_subplot(gs[0, 0])
    ax2 = fig.add_subplot(gs[0, 1])
    ax3 = fig.add_subplot(gs[1, :])   # полная ширина

    # ── Bar 1: фактические расходы по месяцам ────────────────────────────────
    x = np.arange(12)
    max_v = max(monthly_totals) if monthly_totals else 1
    bar_colors = [plt.cm.Blues(0.35 + 0.55 * (v / max_v)) for v in monthly_totals]
    bars = ax1.bar(x, monthly_totals, color=bar_colors,
                   edgecolor='white', linewidth=1.2, width=0.65)
    for bar, v in zip(bars, monthly_totals):
        if v > 0:
            ax1.text(bar.get_x() + bar.get_width() / 2,
                     bar.get_height() + max_v * 0.012,
                     _fmt(v), ha='center', va='bottom', fontsize=11, fontweight='bold', color='#444444')
    ax1.set_xticks(x)
    ax1.set_xticklabels(month_labels, fontsize=12)
    ax1.set_title("Фактические расходы по месяцам",
                  fontsize=20, fontweight='bold', color='#333333', loc='left', pad=20)
    ax1.set_ylabel("Сумма, ₽", fontsize=14, color='#555555')
    ax1.yaxis.set_major_formatter(mticker.FuncFormatter(_rub_formatter))
    ax1.set_ylim(0, max_v * 1.20)
    sns.despine(ax=ax1)

    # ── Bar 2: накопленная структура по категориям ────────────────────────────
    bottom = np.zeros(12)
    for i, cat in enumerate(top_cats_list):
        vals = np.array(stacked[cat])
        color = _get_cat_color(cat, i)
        ax2.bar(x, vals, bottom=bottom, color=color, label=_cap(cat),
                edgecolor='white', linewidth=0.5, width=0.7)
        bottom += vals
    ax2.set_xticks(x)
    ax2.set_xticklabels(month_labels, fontsize=12)
    ax2.set_title("Структура расходов по категориям (накопленная)",
                  fontsize=20, fontweight='bold', color='#333333', loc='left', pad=20)
    ax2.set_ylabel("Сумма, ₽", fontsize=14, color='#555555')
    ax2.yaxis.set_major_formatter(mticker.FuncFormatter(_rub_formatter))
    _n_leg_cols_bar = 1 if len(top_cats_list) <= 6 else 2
    ax2.legend(
        loc='upper left',
        bbox_to_anchor=(1.01, 1.0),
        fontsize=14,
        frameon=False,
        ncol=_n_leg_cols_bar,
        handlelength=1.4,
        handletextpad=0.4,
        labelspacing=0.35,
        borderpad=0,
        columnspacing=0.8,
    )
    sns.despine(ax=ax2)

    # ── Line: расходы по категориям за год ───────────────────────────────────
    for i, cat in enumerate(top_cats_list):
        vals = stacked[cat]
        color = _get_cat_color(cat, i)
        ax3.plot(range(12), vals, marker='o', color=color, linewidth=2,
                 markersize=5, label=_cap(cat), markerfacecolor='white',
                 markeredgewidth=1.5, markeredgecolor=color)
    ax3.set_xticks(range(12))
    ax3.set_xticklabels(month_labels, fontsize=12)
    ax3.set_title("Расходы по категориям — динамика за год",
                  fontsize=20, fontweight='bold', color='#333333', loc='left', pad=20)
    ax3.set_ylabel("Сумма, ₽", fontsize=14, color='#555555')
    ax3.yaxis.set_major_formatter(mticker.FuncFormatter(_rub_formatter))
    _n_leg_cols = 1 if len(top_cats_list) <= 6 else 2
    ax3.legend(
        loc='upper left',
        bbox_to_anchor=(1.01, 1.0),
        fontsize=14,
        frameon=False,
        ncol=_n_leg_cols,
        handlelength=1.4,
        handletextpad=0.4,
        labelspacing=0.35,
        borderpad=0,
        columnspacing=0.8,
    )
    sns.despine(ax=ax3)

    # rect[2]: оставляем место под легенду — шире при 2 столбцах
    _right = 0.84 if _n_leg_cols == 2 else 0.88
    plt.tight_layout(pad=2.0, rect=[0.04, 0, _right, 0.95])
    pdf.savefig(fig, bbox_inches='tight', pad_inches=0.5, facecolor='white')
    plt.close(fig)


# ─── Страница 5: Multi-line chart ────────────────────────────────────────────

def _page_multiline(pdf: PdfPages, df: pd.DataFrame, today: datetime.date):
    months = _rolling_months(today)
    month_labels = [_month_label(y, m, today) for y, m in months]

    top_cats = list(df.groupby('category')['amount'].sum()
                    .sort_values(ascending=False).head(10).index)

    fig, ax = plt.subplots(figsize=(18, 10))
    fig.patch.set_facecolor('white')
    _set_style()

    for i, cat in enumerate(top_cats):
        vals = [float(df[(df['date'].dt.year == y) & (df['date'].dt.month == m) &
                         (df['category'] == cat)]['amount'].sum())
                for y, m in months]
        color = _get_cat_color(cat, i)
        ax.plot(range(12), vals, marker='o', color=color, linewidth=2,
                markersize=5, label=_cap(cat), markerfacecolor='white',
                markeredgewidth=1.5, markeredgecolor=color)

    ax.set_xticks(range(12))
    ax.set_xticklabels(month_labels, fontsize=12)
    ax.set_title("Расходы по категориям — динамика за год",
                 fontsize=20, fontweight='bold', color='#333333', loc='left', pad=20)
    ax.set_ylabel("Сумма, ₽", fontsize=14, color='#555555')
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(_rub_formatter))
    ax.legend(loc='upper left', fontsize=9, frameon=False,
              ncol=2, bbox_to_anchor=(1.01, 1.0))
    sns.despine(ax=ax)

    fig.suptitle("Раздел 2 — Структура расходов",
                 fontsize=25, fontweight='bold', color='#2A2A2A', y=0.95)

    plt.tight_layout(pad=2.0, rect=[0.04, 0, 0.85, 0.94])
    pdf.savefig(fig, bbox_inches='tight', pad_inches=0.5, facecolor='white')
    plt.close(fig)


# ─── Страница 6: Тренды + прогноз + ECDF ────────────────────────────────────

def _page_trends(pdf: PdfPages, df: pd.DataFrame, today: datetime.date):
    months = _rolling_months(today)
    month_labels = [_month_label(y, m, today) for y, m in months]
    monthly_totals = [float(df[(df['date'].dt.year == y) & (df['date'].dt.month == m)]['amount'].sum())
                      for y, m in months]

    # Прогноз: среднее за последние 3-6 ненулевых месяцев
    non_zero_vals = [v for v in monthly_totals if v > 0]
    forecast_window = non_zero_vals[-min(6, len(non_zero_vals)):] if non_zero_vals else []
    forecast_val = np.mean(forecast_window) if forecast_window else 0

    # Линейный тренд через polyfit
    xs = np.array([i for i, v in enumerate(monthly_totals)])
    ys = np.array(monthly_totals, dtype=float)
    if len(xs) >= 2 and ys.max() > 0:
        coeffs = np.polyfit(xs, ys, 1)
        trend_line = np.polyval(coeffs, xs)
        next_trend = float(np.polyval(coeffs, 12))
    else:
        trend_line = ys
        next_trend = forecast_val

    # ECDF — текущий месяц
    cur_df = df[(df['date'].dt.year == today.year) & (df['date'].dt.month == today.month)]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(20, 9))
    fig.patch.set_facecolor('white')
    _set_style()
    fig.suptitle("Раздел 3 — Тренды",
                 fontsize=25, fontweight='bold', color='#2A2A2A', y=0.95)


    # ── Trend-линия ──────────────────────────────────────────────────────────
    max_v = max(max(monthly_totals, default=0), next_trend, 1)

    ax1.fill_between(range(12), monthly_totals, alpha=0.10, color="#4E79A7")
    ax1.plot(range(12), monthly_totals, marker='o', color="#4E79A7",
             linewidth=2.5, markersize=7, markerfacecolor='white',
             markeredgewidth=2.5, markeredgecolor="#4E79A7", label='Факт', zorder=3)
    ax1.plot(range(12), trend_line, '--', color="#E15759", linewidth=1.5,
             alpha=0.7, label='Линейный тренд')

    # Прогноз следующего месяца
    next_m = today.month % 12 + 1
    next_y = today.year if today.month < 12 else today.year + 1
    next_label = f"{MONTH_SHORT_RU[next_m]} {str(next_y)[2:]}"
    ax1.annotate(
        f"Прогноз {next_label}:\n{_fmt(forecast_val)}",
        xy=(11, monthly_totals[-1] if monthly_totals else 0),
        xytext=(10, max_v * 0.85),
        fontsize=9, color='#555555',
        arrowprops=dict(arrowstyle='->', color='#aaaaaa'),
        bbox=dict(boxstyle='round,pad=0.3', facecolor='#fffbe6', edgecolor='#dddddd'),
    )

    ax1.set_xticks(range(12))
    ax1.set_xticklabels(month_labels, fontsize=12)
    ax1.set_title("Тренд расходов за год + прогноз",
                  fontsize=20, fontweight='bold', color='#333333', loc='left', pad=20)
    ax1.set_ylabel("Сумма, ₽", fontsize=14, color='#555555')
    ax1.yaxis.set_major_formatter(mticker.FuncFormatter(_rub_formatter))
    ax1.set_ylim(0, max_v * 1.30)
    ax1.legend(fontsize=9, frameon=False)
    sns.despine(ax=ax1)

    # ── ECDF ─────────────────────────────────────────────────────────────────
    if not cur_df.empty:
        amounts_sorted = np.sort(cur_df['amount'].values.astype(float))
        n = len(amounts_sorted)
        cdf = np.arange(1, n + 1) / n

        ax2.step(amounts_sorted, cdf * 100, color="#59A14F", linewidth=2.5, where='post')
        ax2.fill_between(amounts_sorted, cdf * 100, alpha=0.10, color="#59A14F", step='post')

        for pct in [50, 80, 90, 95]:
            idx = np.searchsorted(cdf, pct / 100, side='left')
            if idx < n:
                val = amounts_sorted[min(idx, n - 1)]
                ax2.axhline(pct, color='#E15759', linestyle='--', linewidth=1, alpha=0.6)
                ax2.axvline(val, color='#E15759', linestyle='--', linewidth=1, alpha=0.6)
                ax2.annotate(f"{pct}% ≤ {_fmt(val)}",
                             xy=(val, pct),
                             xytext=(val + amounts_sorted.max() * 0.05, pct - 4),
                             fontsize=8, color='#E15759',
                             arrowprops=dict(arrowstyle='->', color='#E15759', lw=0.8))

        ax2.set_xlabel("Сумма покупки, ₽", fontsize=14, color='#555555')
        ax2.set_ylabel("Доля транзакций, %", fontsize=14, color='#555555')
        ax2.xaxis.set_major_formatter(mticker.FuncFormatter(_rub_formatter))
        ax2.set_ylim(0, 105)
        ax2.set_title(
            f"ECDF покупок — {MONTH_NAMES_RU[today.month]} {today.year}",
            fontsize=20, fontweight='bold', color='#333333', loc='left', pad=20)
        sns.despine(ax=ax2)
    else:
        ax2.text(0.5, 0.5, f"Нет данных\nза {MONTH_NAMES_RU[today.month]} {today.year}",
                 ha='center', va='center', fontsize=12, color='#999999',
                 transform=ax2.transAxes)
        ax2.axis('off')

    plt.tight_layout(pad=2.0, rect=[0.04, 0, 1, 0.94])
    pdf.savefig(fig, bbox_inches='tight', pad_inches=0.5, facecolor='white')
    plt.close(fig)


# ─── Страница 7: Heatmaps ─────────────────────────────────────────────────────

def _page_heatmaps(pdf: PdfPages, df: pd.DataFrame, today: datetime.date):
    months = _rolling_months(today)

    df2 = df.copy()
    df2['weekday'] = df2['date'].dt.weekday   # 0=Пн … 6=Вс
    df2['day_of_month'] = df2['date'].dt.day
    df2['month_num'] = df2['date'].dt.month
    df2['year_num'] = df2['date'].dt.year

    # HM1: avg by weekday (single row)
    hm1_data = df2.groupby('weekday')['amount'].mean().reindex(range(7), fill_value=0)

    # HM2: avg by (year*100+month, day_of_month)
    month_idx = {(y, m): i for i, (y, m) in enumerate(months)}
    df2['month_idx'] = df2.apply(
        lambda r: month_idx.get((r['year_num'], r['month_num']), -1), axis=1
    )
    df2_valid = df2[df2['month_idx'] >= 0]

    pivot2 = pd.pivot_table(df2_valid, values='amount', index='month_idx',
                            columns='day_of_month', aggfunc='sum', fill_value=0)
    # Ensure all 31 columns exist
    for d in range(1, 32):
        if d not in pivot2.columns:
            pivot2[d] = 0.0
    pivot2 = pivot2[sorted(pivot2.columns)]
    pivot2_labels = [_month_label(y, m, today) for y, m in months]

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(18, 16),
                                   gridspec_kw={'height_ratios': [1, 4]})
    fig.patch.set_facecolor('white')
    _set_style()
    fig.suptitle("Раздел 4 — Паттерны",
                 fontsize=25, fontweight='bold', color='#2A2A2A', y=0.95)

    # HM1
    hm1_array = hm1_data.values.reshape(1, 7)
    sns.heatmap(
        pd.DataFrame(hm1_array, columns=WEEKDAY_SHORT_RU),
        ax=ax1, cmap='YlOrRd', annot=True,
        fmt='.0f', linewidths=0.5, linecolor='white',
        cbar_kws={'label': '₽'},
        annot_kws={'fontsize': 14},
    )
    for _coll in ax1.collections:
        _coll.set_alpha(0.9)
    ax1.set_title("Средние расходы по дням недели, ₽",
                  fontsize=20, fontweight='bold', color='#333333', loc='left', pad=20)
    ax1.set_ylabel('')
    ax1.set_yticklabels([])

    # HM2
    sns.heatmap(
        pivot2, ax=ax2, cmap='YlOrRd',
        linewidths=0.3, linecolor='white',
        cbar_kws={'label': '₽'},
        yticklabels=pivot2_labels,
    )
    for _coll in ax2.collections:
        _coll.set_alpha(0.9)
    ax2.set_title("Суммы расходов по дням месяца × месяцам, ₽",
                  fontsize=20, fontweight='bold', color='#333333', loc='left', pad=20)
    ax2.set_xlabel("День месяца", fontsize=14, color='#555555')
    ax2.set_ylabel("")
    ax2.tick_params(axis='y', labelsize=12, rotation=0)

    plt.tight_layout(pad=2.0, rect=[0.04, 0, 1, 0.94])
    pdf.savefig(fig, bbox_inches='tight', pad_inches=0.5, facecolor='white')
    plt.close(fig)


# ─── Страница 8: Scatter plots ────────────────────────────────────────────────

def _page_scatter(pdf: PdfPages, df: pd.DataFrame, today: datetime.date):
    cur_y, cur_m = today.year, today.month
    cur_df = df[(df['date'].dt.year == cur_y) & (df['date'].dt.month == cur_m)].copy()

    months = _rolling_months(today)
    month_idx = {(y, m): i for i, (y, m) in enumerate(months)}
    df2 = df.copy()
    df2['month_idx'] = df2.apply(
        lambda r: month_idx.get((r['date'].dt.year if hasattr(r['date'], 'dt') else r['date'].year,
                                  r['date'].dt.month if hasattr(r['date'], 'dt') else r['date'].month), -1),
        axis=1
    )

    # Фиксируем: дата — это pd.Timestamp
    df3 = df.copy()
    df3['year_num'] = df3['date'].dt.year
    df3['month_num'] = df3['date'].dt.month
    df3['month_idx'] = df3.apply(lambda r: month_idx.get((r['year_num'], r['month_num']), -1), axis=1)

    # Категории текущего месяца для цвета
    cur_cats = sorted(cur_df['category'].unique()) if not cur_df.empty else []
    cat_color_map = {cat: _get_cat_color(cat, i) for i, cat in enumerate(cur_cats)}

    fig, axes = plt.subplots(1, 2, figsize=(18, 9))
    fig.patch.set_facecolor('white')
    _set_style()
    fig.suptitle("Раздел 4 — Паттерны",
                 fontsize=25, fontweight='bold', color='#2A2A2A', y=0.98)


    # ── Scatter 1: сумма × день месяца ───────────────────────────────────────
    ax1 = axes[0]
    if not cur_df.empty:
        cur_df2 = cur_df.copy()
        cur_df2['day'] = cur_df2['date'].dt.day
        for cat in cur_cats:
            sub = cur_df2[cur_df2['category'] == cat]
            ax1.scatter(sub['amount'], sub['day'],
                        color=cat_color_map[cat], alpha=0.75, s=60,
                        label=_cap(cat), edgecolors='white', linewidth=0.5)
        ax1.set_xlabel("Сумма покупки, ₽", fontsize=14, color='#555555')
        ax1.set_ylabel("День месяца", fontsize=14, color='#555555')
        ax1.xaxis.set_major_formatter(mticker.FuncFormatter(_rub_formatter))
        ax1.set_yticks(range(1, today.day + 1))
        ax1.legend(fontsize=7, frameon=False, ncol=2, loc='lower right')
        ax1.set_title("Покупки: сумма × день месяца",
                      fontsize=20, fontweight='bold', color='#333333', loc='left', pad=20)
        sns.despine(ax=ax1)
    else:
        ax1.text(0.5, 0.5, 'Нет данных', ha='center', va='center',
                 fontsize=12, color='#999999', transform=ax1.transAxes)
        ax1.axis('off')

    # ── Scatter 2: сумма × час ────────────────────────────────────────────────
    ax2 = axes[1]
    if not cur_df.empty and 'time' in cur_df.columns:
        cur_df3 = cur_df.copy()
        cur_df3['hour'] = cur_df3['time'].apply(
            lambda t: t.hour if hasattr(t, 'hour') else (t.seconds // 3600 if hasattr(t, 'seconds') else 0)
        )
        for cat in cur_cats:
            sub = cur_df3[cur_df3['category'] == cat]
            ax2.scatter(sub['amount'], sub['hour'],
                        color=cat_color_map[cat], alpha=0.75, s=60,
                        label=_cap(cat), edgecolors='white', linewidth=0.5)
        ax2.set_xlabel("Сумма покупки, ₽", fontsize=14, color='#555555')
        ax2.set_ylabel("Час дня (0–23)", fontsize=14, color='#555555')
        ax2.xaxis.set_major_formatter(mticker.FuncFormatter(_rub_formatter))
        ax2.set_yticks(range(0, 24, 2))
        ax2.legend(fontsize=7, frameon=False, ncol=2, loc='lower right')
        ax2.set_title("Покупки: сумма × час дня",
                      fontsize=20, fontweight='bold', color='#333333', loc='left', pad=20)
        sns.despine(ax=ax2)
    else:
        ax2.text(0.5, 0.5, 'Нет данных', ha='center', va='center',
                 fontsize=12, color='#999999', transform=ax2.transAxes)
        ax2.axis('off')

    plt.tight_layout(pad=2.0, rect=[0.04, 0, 1, 0.94])
    pdf.savefig(fig, bbox_inches='tight', pad_inches=0.5, facecolor='white')
    plt.close(fig)


# ─── Страница 9: Scatter-3 (год) + Heatmap-3 (кат × д. недели) ──────────────

def _page_scatter3_hm3(pdf: PdfPages, df: pd.DataFrame, today: datetime.date):
    months = _rolling_months(today)
    month_idx = {(y, m): i for i, (y, m) in enumerate(months)}
    month_color = {(y, m): PALETTE[i % len(PALETTE)] for i, (y, m) in enumerate(months)}

    df2 = df.copy()
    df2['year_num'] = df2['date'].dt.year
    df2['month_num'] = df2['date'].dt.month
    df2['day_of_month'] = df2['date'].dt.day
    df2['weekday'] = df2['date'].dt.weekday

    # Scatter 3: агрегат по дате (день)
    day_agg = df2.groupby(['date']).agg(
        total=('amount', 'sum'),
        count=('amount', 'count'),
        year_num=('year_num', 'first'),
        month_num=('month_num', 'first'),
        day_of_month=('day_of_month', 'first'),
    ).reset_index()
    day_agg['color'] = day_agg.apply(
        lambda r: month_color.get((r['year_num'], r['month_num']), '#999999'), axis=1
    )
    day_agg['month_idx'] = day_agg.apply(
        lambda r: month_idx.get((r['year_num'], r['month_num']), -1), axis=1
    )
    day_agg = day_agg[day_agg['month_idx'] >= 0]

    # HM3: категория × день недели
    top_cats = list(df.groupby('category')['amount'].sum()
                    .sort_values(ascending=False).head(10).index)
    hm3_data = pd.pivot_table(
        df2[df2['category'].isin(top_cats)],
        values='amount',
        index='category',
        columns='weekday',
        aggfunc='sum',
        fill_value=0,
    )
    hm3_data.columns = [WEEKDAY_SHORT_RU[c] for c in hm3_data.columns]
    hm3_data.index = [_cap(c) for c in hm3_data.index]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(20, 10))
    fig.patch.set_facecolor('white')
    _set_style()
    fig.suptitle("Раздел 4 — Паттерны",
                 fontsize=25, fontweight='bold', color='#2A2A2A', y=0.95)

    # ── Scatter 3 ─────────────────────────────────────────────────────────────
    if not day_agg.empty:
        sc = ax1.scatter(
            day_agg['day_of_month'], day_agg['total'],
            s=day_agg['count'] * 30,
            c=day_agg['color'],
            alpha=0.70, edgecolors='white', linewidth=0.5,
        )
        ax1.set_xlabel("День месяца (1–31)", fontsize=14, color='#555555')
        ax1.set_ylabel("Сумма трат за день, ₽", fontsize=14, color='#555555')
        ax1.yaxis.set_major_formatter(mticker.FuncFormatter(_rub_formatter))
        ax1.set_xticks(range(1, 32, 2))

        # Легенда месяцев
        legend_patches = [
            mpatches.Patch(color=month_color[(y, m)],
                           label=_month_label(y, m, today))
            for y, m in months
        ]
        ax1.legend(handles=legend_patches, fontsize=8, frameon=False,
                   ncol=2, loc='upper right')
        ax1.set_title(
            "Сумма трат в день × день месяца\n(размер = кол-во транзакций, цвет = месяц)",
            fontsize=20, fontweight='bold', color='#333333', loc='left', pad=20,
        )
        sns.despine(ax=ax1)
    else:
        ax1.text(0.5, 0.5, 'Нет данных', ha='center', va='center',
                 fontsize=12, color='#999999', transform=ax1.transAxes)
        ax1.axis('off')

    # ── HM3 ──────────────────────────────────────────────────────────────────
    if not hm3_data.empty:
        sns.heatmap(
            hm3_data, ax=ax2, cmap='YlOrRd',
            annot=True, fmt='.0f',
            linewidths=0.5, linecolor='white',
            cbar_kws={'label': '₽'},
            annot_kws={'fontsize': 14},
        )
        for _coll in ax2.collections:
            _coll.set_alpha(0.9)
        ax2.set_title("Расходы по категориям × дням недели, ₽",
                      fontsize=20, fontweight='bold', color='#333333', loc='left', pad=20)
        ax2.set_xlabel("День недели", fontsize=14, color='#555555')
        ax2.set_ylabel("")
        ax2.tick_params(axis='y', labelsize=12, rotation=0)
    else:
        ax2.text(0.5, 0.5, 'Нет данных', ha='center', va='center',
                 fontsize=12, color='#999999', transform=ax2.transAxes)
        ax2.axis('off')

    plt.tight_layout(pad=2.0, rect=[0.04, 0, 1, 0.94])
    pdf.savefig(fig, bbox_inches='tight', pad_inches=0.5, facecolor='white')
    plt.close(fig)


# ─── Страница 10: Box plots ───────────────────────────────────────────────────

def _page_boxplots(pdf: PdfPages, df: pd.DataFrame, today: datetime.date):
    months = _rolling_months(today)
    month_labels = [_month_label(y, m, today) for y, m in months]

    df2 = df.copy()
    df2['year_num'] = df2['date'].dt.year
    df2['month_num'] = df2['date'].dt.month
    month_idx = {(y, m): i for i, (y, m) in enumerate(months)}
    df2['month_idx'] = df2.apply(
        lambda r: month_idx.get((r['year_num'], r['month_num']), -1), axis=1
    )
    df2 = df2[df2['month_idx'] >= 0]

    # Текущий месяц для Box 2
    cur_y, cur_m = today.year, today.month
    cur_df = df[(df['date'].dt.year == cur_y) & (df['date'].dt.month == cur_m)]
    top_cats = list(cur_df.groupby('category')['amount'].sum()
                    .sort_values(ascending=False).head(8).index)

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(18, 18))
    fig.patch.set_facecolor('white')
    _set_style()
    fig.suptitle("Раздел 4 — Паттерны",
                 fontsize=25, fontweight='bold', color='#2A2A2A', y=0.95)

    # ── Box 1: месяц × сумма ─────────────────────────────────────────────────
    if not df2.empty:
        box_data = [df2[df2['month_idx'] == i]['amount'].values for i in range(12)]
        bp = ax1.boxplot(
            box_data, patch_artist=True, notch=False,
            medianprops=dict(color='#E15759', linewidth=2),
            flierprops=dict(marker='o', markersize=4, markerfacecolor='#F28E2B',
                            markeredgecolor='white', alpha=0.8),
            whiskerprops=dict(linewidth=1.2, color='#666666'),
            capprops=dict(linewidth=1.2, color='#666666'),
        )
        for patch, color in zip(bp['boxes'], PALETTE):
            patch.set_facecolor(color)
            patch.set_alpha(0.6)
        ax1.margins(x=0.05) # left margin 

        ax1.set_xticks(range(1, 13))
        ax1.set_xticklabels(month_labels, fontsize=12)
        ax1.set_title("Распределение сумм покупок по месяцам",
                      fontsize=20, fontweight='bold', color='#333333', loc='left', pad=20)
        ax1.set_ylabel("Сумма покупки, ₽", fontsize=14, color='#555555')
        ax1.yaxis.set_major_formatter(mticker.FuncFormatter(_rub_formatter))

        # Подпись 3 самых крупных выбросов
        fliers_all = []
        for i, vals in enumerate(box_data):
            if len(vals) == 0:
                continue
            q1, q3 = np.percentile(vals, 25), np.percentile(vals, 75)
            iqr = q3 - q1
            upper = q3 + 1.5 * iqr
            for v in vals:
                if v > upper:
                    year_m, month_m = months[i]
                    # Ищем покупку в DF
                    sub = df2[(df2['month_idx'] == i) & (df2['amount'] == v)]
                    if not sub.empty:
                        row = sub.iloc[0]
                        desc_raw = str(row['description']) if pd.notna(row.get('description', None)) and row['description'] else ''
                        label_txt = f"{_fmt(v)}\n{_cap(row['category'])}\n{row['date'].date()}"
                    else:
                        label_txt = _fmt(v)
                    fliers_all.append((float(v), i + 1, label_txt))

        fliers_all.sort(key=lambda x: -x[0])
        for val, x_pos, label in fliers_all[:3]:
            ax1.annotate(label, xy=(x_pos, val),
                         xytext=(x_pos + 0.5, val * 1.05),
                         fontsize=7, color='#E15759',
                         arrowprops=dict(arrowstyle='->', color='#cccccc', lw=0.8),
                         bbox=dict(boxstyle='round,pad=0.2', facecolor='white',
                                   edgecolor='#dddddd', alpha=0.9))
        sns.despine(ax=ax1)
    else:
        ax1.text(0.5, 0.5, 'Нет данных', ha='center', va='center',
                 fontsize=12, color='#999999', transform=ax1.transAxes)
        ax1.axis('off')

    # ── Box 2: категории × сумма (текущий/последний месяц) ───────────────────
    if not cur_df.empty and top_cats:
        box_data2 = [cur_df[cur_df['category'] == cat]['amount'].values for cat in top_cats]
        bp2 = ax2.boxplot(
            box_data2, patch_artist=True, notch=False,
            medianprops=dict(color='#E15759', linewidth=2),
            flierprops=dict(marker='o', markersize=5, markerfacecolor='#F28E2B',
                            markeredgecolor='white', alpha=0.8),
            whiskerprops=dict(linewidth=1.2, color='#666666'),
            capprops=dict(linewidth=1.2, color='#666666'),
        )
        for patch, cat in zip(bp2['boxes'], top_cats):
            patch.set_facecolor(_get_cat_color(cat, 0))
            patch.set_alpha(0.6)

        ax2.set_xticks(range(1, len(top_cats) + 1))
        ax2.set_xticklabels([_cap(c) for c in top_cats], fontsize=12)
        ax2.set_title(
            f"Распределение сумм по категориям — {MONTH_NAMES_RU[cur_m]} {cur_y}",
            fontsize=20, fontweight='bold', color='#333333', loc='left', pad=20,
        )
        ax2.set_ylabel("Сумма покупки, ₽", fontsize=14, color='#555555')
        ax2.yaxis.set_major_formatter(mticker.FuncFormatter(_rub_formatter))

        # Подписи выбросов
        fliers2 = []
        for i, cat in enumerate(top_cats):
            vals = cur_df[cur_df['category'] == cat]['amount'].values.astype(float)
            if len(vals) < 2:
                continue
            q1, q3 = np.percentile(vals, 25), np.percentile(vals, 75)
            iqr = q3 - q1
            upper = q3 + 1.5 * iqr
            for v in vals:
                if v > upper:
                    fliers2.append((float(v), i + 1, _fmt(v)))

        fliers2.sort(key=lambda x: -x[0])
        for val, x_pos, label in fliers2[:4]:
            ax2.annotate(label, xy=(x_pos, val),
                         xytext=(x_pos + 0.4, val * 1.05),
                         fontsize=8, color='#E15759',
                         arrowprops=dict(arrowstyle='->', color='#cccccc', lw=0.8),
                         bbox=dict(boxstyle='round,pad=0.2', facecolor='white',
                                   edgecolor='#dddddd', alpha=0.9))
        sns.despine(ax=ax2)
    else:
        ax2.text(0.5, 0.5,
                 f"Нет данных за {MONTH_NAMES_RU[cur_m]} {cur_y}",
                 ha='center', va='center', fontsize=12, color='#999999',
                 transform=ax2.transAxes)
        ax2.axis('off')

    plt.tight_layout(pad=2.0, rect=[0.04, 0, 1, 0.94])
    pdf.savefig(fig, bbox_inches='tight', pad_inches=0.5, facecolor='white')
    plt.close(fig)


def _page_income_overview(
    pdf: PdfPages,
    expense_df: pd.DataFrame,
    income_df: pd.DataFrame,
    today: datetime.date,
    top_n: int = 5,
):
    """Страница отчета с аналитикой по доходам и балансу."""
    _set_style()
    months = _rolling_months(today)
    month_labels = [_month_label(y, m, today) for y, m in months]

    income_df = income_df.copy()
    income_df["date"] = pd.to_datetime(income_df["date"])
    income_df["amount"] = income_df["amount"].astype(float)
    expense_df = expense_df.copy()
    expense_df["date"] = pd.to_datetime(expense_df["date"])
    expense_df["amount"] = expense_df["amount"].astype(float)

    fig = plt.figure(figsize=(22, 14))
    fig.patch.set_facecolor("white")
    fig.suptitle("Раздел доходов", fontsize=25, fontweight="bold", color="#2A2A2A", y=0.97)

    grid = fig.add_gridspec(2, 2, height_ratios=[1, 1], width_ratios=[1, 1], hspace=0.25, wspace=0.22)
    ax_bar = fig.add_subplot(grid[0, 0])
    ax_pie = fig.add_subplot(grid[0, 1])
    ax_cmp = fig.add_subplot(grid[1, 0])
    ax_net = fig.add_subplot(grid[1, 1])

    # Доходы по категориям (top N)
    cat_totals = income_df.groupby("category")["amount"].sum().sort_values(ascending=False)
    if cat_totals.empty:
        ax_bar.text(0.5, 0.5, "Нет данных по доходам", ha="center", va="center", transform=ax_bar.transAxes)
        ax_pie.text(0.5, 0.5, "Нет данных по доходам", ha="center", va="center", transform=ax_pie.transAxes)
        ax_bar.axis("off")
        ax_pie.axis("off")
    else:
        if len(cat_totals) > top_n:
            top = cat_totals.head(top_n)
            other_sum = cat_totals.iloc[top_n:].sum()
            if other_sum > 0:
                top["прочее"] = float(other_sum)
            cat_totals = top

        bar_categories = [str(cat).capitalize() for cat in cat_totals.index]
        bar_values = [float(v) for v in cat_totals.values]
        bar_colors = ["#4CAF50", "#66BB6A", "#81C784", "#A5D6A7", "#C8E6C9", "#AED581"][:len(bar_values)]

        bars = ax_bar.barh(bar_categories, bar_values, color=bar_colors, edgecolor="white", linewidth=1.2)
        ax_bar.invert_yaxis()
        ax_bar.set_title("Доходы по категориям", fontsize=18, fontweight="bold", loc="left")
        ax_bar.xaxis.set_major_formatter(mticker.FuncFormatter(_rub_formatter))
        for bar, value in zip(bars, bar_values):
            ax_bar.text(bar.get_width() * 1.01, bar.get_y() + bar.get_height() / 2, _fmt(value), va="center", fontsize=10)
        sns.despine(ax=ax_bar, left=True, bottom=False)

        pie_colors = bar_colors
        ax_pie.pie(bar_values, labels=bar_categories, autopct="%1.1f%%", startangle=90, colors=pie_colors)
        ax_pie.set_title(f"Доли категорий доходов (top {top_n})", fontsize=18, fontweight="bold")

    # Доходы vs расходы по месяцам
    income_monthly = []
    expense_monthly = []
    net_monthly = []
    for y, m in months:
        income_sum = float(income_df[(income_df["date"].dt.year == y) & (income_df["date"].dt.month == m)]["amount"].sum())
        expense_sum = float(expense_df[(expense_df["date"].dt.year == y) & (expense_df["date"].dt.month == m)]["amount"].sum())
        income_monthly.append(income_sum)
        expense_monthly.append(expense_sum)
        net_monthly.append(income_sum - expense_sum)

    x = np.arange(len(months))
    width = 0.36
    ax_cmp.bar(x - width / 2, income_monthly, width=width, label="Доходы", color="#4CAF50")
    ax_cmp.bar(x + width / 2, expense_monthly, width=width, label="Расходы", color="#E15759")
    ax_cmp.set_xticks(x)
    ax_cmp.set_xticklabels(month_labels, fontsize=10)
    ax_cmp.set_title("Доходы vs расходы по месяцам", fontsize=18, fontweight="bold", loc="left")
    ax_cmp.yaxis.set_major_formatter(mticker.FuncFormatter(_rub_formatter))
    ax_cmp.legend(frameon=False)
    sns.despine(ax=ax_cmp, left=False, bottom=False)

    # Тренд чистого баланса
    ax_net.axhline(0, color="#999999", linewidth=1.0, linestyle="--")
    ax_net.plot(x, net_monthly, marker="o", linewidth=2.5, color="#2E7D32")
    ax_net.fill_between(x, 0, net_monthly, where=np.array(net_monthly) >= 0, alpha=0.15, color="#66BB6A")
    ax_net.fill_between(x, 0, net_monthly, where=np.array(net_monthly) < 0, alpha=0.15, color="#E15759")
    ax_net.set_xticks(x)
    ax_net.set_xticklabels(month_labels, fontsize=10)
    ax_net.set_title("Тренд чистого баланса (доходы - расходы)", fontsize=18, fontweight="bold", loc="left")
    ax_net.yaxis.set_major_formatter(mticker.FuncFormatter(_rub_formatter))
    sns.despine(ax=ax_net, left=False, bottom=False)

    pdf.savefig(fig, bbox_inches="tight", pad_inches=0.5, facecolor="white")
    plt.close(fig)


# ─── Главная синхронная функция рендеринга ────────────────────────────────────

def _render_full_report(df: pd.DataFrame, income_df: pd.DataFrame, today: datetime.date, save_path: str):
    """Рендерит все страницы PDF синхронно. Вызывается в ThreadPoolExecutor."""
    _set_style()

    # Убеждаемся, что date — это datetime
    df = df.copy()
    df['date'] = pd.to_datetime(df['date'])
    df['amount'] = df['amount'].astype(float)

    with PdfPages(save_path) as pdf:
        # Метаданные PDF
        d = pdf.infodict()
        d['Title'] = f'Отчёт по финансам — {MONTH_NAMES_RU[today.month]} {today.year}'
        d['Author'] = 'Telegram Expense Bot'
        d['Subject'] = 'Анализ личных финансов'

        _page_overview(pdf, df, today)           # Стр. 1: обзор (KPI + line + топ-5 + pivot)
        _page_structure_table(pdf, df, today)    # Стр. 2: сводная таблица + 4 круговых диаграммы
        _page_bar_charts(pdf, df, today)         # Стр. 4: 2 гистограммы + line расходы по категориям
        _page_trends(pdf, df, today)             # Стр. 6: тренд + ECDF
        _page_heatmaps(pdf, df, today)           # Стр. 7: heatmaps (д. недели + д. месяца)
        _page_scatter(pdf, df, today)            # Стр. 8: scatter 1+2 (тек. месяц)
        _page_scatter3_hm3(pdf, df, today)       # Стр. 9: scatter 3 + heatmap кат×д.нед.
        _page_boxplots(pdf, df, today)           # Стр. 10: box plots
        if income_df is not None and not income_df.empty:
            _page_income_overview(pdf, df, income_df, today, top_n=5)

    return save_path


# ─── Публичная async-функция ─────────────────────────────────────────────────

async def generate_pdf_report(user_id, project_id=None) -> Optional[str]:
    """
    Генерирует PDF-отчёт по расходам за скользящие 12 месяцев.
    Возвращает путь к PDF-файлу или None если данных нет.
    """
    today = datetime.date.today()
    cur_year = today.year
    prev_year = cur_year - 1

    # Загружаем расходы и доходы за 2 года (нужны для скользящего окна 12 месяцев)
    df_cur, df_prev, income_cur, income_prev = await asyncio.gather(
        excel.get_all_expenses(user_id, cur_year, project_id),
        excel.get_all_expenses(user_id, prev_year, project_id),
        income_utils.get_all_incomes(user_id, cur_year, project_id),
        income_utils.get_all_incomes(user_id, prev_year, project_id),
    )

    frames = []
    if df_cur is not None and not df_cur.empty:
        frames.append(df_cur)
    if df_prev is not None and not df_prev.empty:
        frames.append(df_prev)

    if not frames:
        return None

    df_all = pd.concat(frames, ignore_index=True)
    df_all['date'] = pd.to_datetime(df_all['date'])
    df_all['amount'] = df_all['amount'].astype(float)

    # Фильтруем: скользящие 12 месяцев
    cutoff = today.replace(day=1)
    # Сдвигаем на 11 месяцев назад (начало окна = 12-й месяц назад включая текущий)
    m = cutoff.month - 11
    y = cutoff.year
    while m <= 0:
        m += 12
        y -= 1
    window_start = datetime.date(y, m, 1)
    df_all = df_all[df_all['date'].dt.date >= window_start]

    if df_all.empty:
        return None

    income_frames = []
    if income_cur is not None and not income_cur.empty:
        income_frames.append(income_cur)
    if income_prev is not None and not income_prev.empty:
        income_frames.append(income_prev)

    income_all = pd.DataFrame(columns=["date", "amount", "category", "description", "created_at"])
    if income_frames:
        income_all = pd.concat(income_frames, ignore_index=True)
        income_all["date"] = pd.to_datetime(income_all["date"])
        income_all["amount"] = income_all["amount"].astype(float)
        income_all = income_all[income_all["date"].dt.date >= window_start]

    user_dir = excel.create_user_dir(user_id)
    save_path = os.path.join(user_dir, f"report_{today.strftime('%Y%m%d')}.pdf")

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None,
        functools.partial(_render_full_report, df_all, income_all, today, save_path),
    )
