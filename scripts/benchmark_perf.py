"""
Benchmark script for measuring chart generation and Excel export performance.
Run before and after performance optimizations to measure improvement.

Usage: python scripts/benchmark_perf.py
"""

import time
import sys
import os
import tempfile

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import seaborn as sns
import pandas as pd


def benchmark_pie_chart(n: int = 5) -> list[float]:
    """Benchmark a donut pie chart similar to create_monthly_pie_chart."""
    times = []
    categories = ["Еда", "Транспорт", "Кафе", "Развлечения", "Здоровье", "Одежда", "Прочее", "ЖКХ"]
    amounts = [15000, 8000, 5000, 4000, 3000, 2500, 2000, 1500]
    total = sum(amounts)

    for _ in range(n):
        t0 = time.perf_counter()
        fig, ax = plt.subplots(figsize=(10, 6.5))
        fig.patch.set_facecolor('white')
        fig.subplots_adjust(left=0.01, right=0.80, top=0.82, bottom=0.03)
        wedges, _ = ax.pie(
            amounts,
            labels=None,
            startangle=90,
            wedgeprops=dict(width=0.50, edgecolor='white', linewidth=0.5),
            counterclock=False,
        )
        ax.text(0, 0, f"{total:,} руб.", ha='center', va='center', fontsize=16, fontweight=600)
        tmp = tempfile.mktemp(suffix='.png')
        plt.savefig(tmp, bbox_inches='tight', facecolor='white', dpi=150)
        plt.close(fig)
        os.unlink(tmp)
        times.append(time.perf_counter() - t0)
    return times


def benchmark_bar_chart(n: int = 5) -> list[float]:
    """Benchmark a bar chart similar to create_monthly_bar_chart."""
    times = []
    months = ['Янв', 'Фев', 'Мар', 'Апр', 'Май', 'Июн',
              'Июл', 'Авг', 'Сен', 'Окт', 'Ноя', 'Дек']
    amounts = [10000, 12000, 8000, 15000, 11000, 9000,
               13000, 14000, 10500, 12500, 11500, 16000]

    for _ in range(n):
        t0 = time.perf_counter()
        fig, ax = plt.subplots(figsize=(12, 6))
        fig.patch.set_facecolor('white')
        ax.bar(months, amounts, color='steelblue', edgecolor='white', linewidth=1.5, width=0.65)
        ax.set_title("Расходы по месяцам", fontsize=12, fontweight='bold')
        ax.yaxis.set_major_formatter(
            mticker.FuncFormatter(lambda x, _: f"{int(x):,}")
        )
        tmp = tempfile.mktemp(suffix='.png')
        plt.savefig(tmp, bbox_inches='tight', facecolor='white')
        plt.close(fig)
        os.unlink(tmp)
        times.append(time.perf_counter() - t0)
    return times


def benchmark_excel_generation(n: int = 5) -> list[float]:
    """Benchmark Excel file generation similar to perform_export."""
    times = []
    # Create a realistic DataFrame with 500 rows
    import datetime
    import random
    random.seed(42)
    cats = ["Еда", "Транспорт", "Кафе", "Развлечения", "Здоровье"]
    rows = []
    for i in range(500):
        d = datetime.date(2024, random.randint(1, 12), random.randint(1, 28))
        rows.append({
            'date': d,
            'month': d.month,
            'category': random.choice(cats),
            'amount': round(random.uniform(100, 5000), 2),
            'description': f'Расход {i}',
        })
    expenses_df = pd.DataFrame(rows)
    expenses_df['amount'] = pd.to_numeric(expenses_df['amount'])

    for _ in range(n):
        t0 = time.perf_counter()
        tmp = tempfile.mktemp(suffix='.xlsx')
        with pd.ExcelWriter(tmp, engine='openpyxl') as writer:
            expenses_df.to_excel(writer, sheet_name='Все расходы', index=False)
            category_stats = expenses_df.groupby('category')['amount'].agg(['sum', 'count', 'mean']).round(2)
            category_stats.columns = ['Общая сумма', 'Количество', 'Средняя сумма']
            category_stats.to_excel(writer, sheet_name='Статистика по категориям')
            monthly_stats = expenses_df.groupby('month')['amount'].agg(['sum', 'count', 'mean']).round(2)
            monthly_stats.columns = ['Общая сумма', 'Количество', 'Средняя сумма']
            monthly_stats.to_excel(writer, sheet_name='Статистика по месяцам')
            top_expenses = expenses_df.nlargest(10, 'amount')[['date', 'category', 'amount', 'description']]
            top_expenses.to_excel(writer, sheet_name='Топ-10 расходов', index=False)
        os.unlink(tmp)
        times.append(time.perf_counter() - t0)
    return times


def report(label: str, times: list[float]) -> None:
    avg = sum(times) / len(times) * 1000
    mn = min(times) * 1000
    mx = max(times) * 1000
    print(f"  {label:<30} avg={avg:7.1f} ms  min={mn:6.1f} ms  max={mx:6.1f} ms")


def main():
    n = 5
    print(f"=== Benchmark (n={n} iterations each) ===\n")

    print("Warming up matplotlib...")
    fig, ax = plt.subplots()
    plt.close(fig)

    print("\nRunning benchmarks...\n")

    pie_times = benchmark_pie_chart(n)
    bar_times = benchmark_bar_chart(n)
    excel_times = benchmark_excel_generation(n)

    print("Results:")
    report("Pie chart (donut):", pie_times)
    report("Bar chart (monthly):", bar_times)
    report("Excel export (500 rows):", excel_times)

    total_sequential = (sum(pie_times) + sum(bar_times)) / n * 1000
    print(f"\n  {'Pie+Bar sequential (avg):':<30} {total_sequential:7.1f} ms")
    # After optimization 3 (asyncio.gather), they run in parallel
    parallel_estimate = max(sum(pie_times) / n, sum(bar_times) / n) * 1000
    print(f"  {'Pie+Bar parallel estimate:':<30} {parallel_estimate:7.1f} ms")
    print(f"  {'Savings from parallelism:':<30} {total_sequential - parallel_estimate:7.1f} ms")

    print("\n=== Done ===")


if __name__ == '__main__':
    main()
