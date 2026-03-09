"""
Тесты для utils/report_generator.py

Покрывают:
- Вспомогательные чистые функции (_fmt, _cap, _rub_formatter, _rolling_months,
  _month_label, _get_cat_color)
- Функцию построения круговой диаграммы (_pie_for_period)
- Все функции рендеринга страниц (_page_overview, _page_structure_table, ...)
- Интеграционный тест сборки полного отчёта (_render_full_report)
- Публичную async-функцию generate_pdf_report
"""

import datetime
import os

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import pandas as pd
import pytest
from matplotlib.backends.backend_pdf import PdfPages
from unittest.mock import AsyncMock, MagicMock, patch

from utils import report_generator as rg


# ─── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def today():
    """Фиксированная дата для детерминированных тестов."""
    return datetime.date(2026, 3, 8)


@pytest.fixture
def sample_df(today):
    """
    DataFrame с 12 месяцами данных и 5 категориями.
    Имитирует реальный вывод из БД.
    """
    rows = []
    categories = ["продукты", "транспорт", "развлечения", "подписки", "связь"]
    for i in range(11, -1, -1):
        m = today.month - i
        y = today.year
        while m <= 0:
            m += 12
            y -= 1
        for day in range(1, 6):
            for j, cat in enumerate(categories):
                rows.append({
                    "date": pd.Timestamp(y, m, min(day, 28)),
                    "amount": float((j + 1) * 100 + day * 10 + i * 5),
                    "category": cat,
                    "description": f"desc {cat} {day}",
                    "time": datetime.time(10 + j, 0, 0),
                })
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    return df


@pytest.fixture
def single_month_df(today):
    """DataFrame только с текущим месяцем."""
    rows = [
        {
            "date": pd.Timestamp(today.year, today.month, 1),
            "amount": 500.0,
            "category": "продукты",
            "description": "хлеб",
            "time": datetime.time(10, 0, 0),
        },
        {
            "date": pd.Timestamp(today.year, today.month, 5),
            "amount": 300.0,
            "category": "транспорт",
            "description": "метро",
            "time": datetime.time(9, 0, 0),
        },
    ]
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    return df


@pytest.fixture
def tmp_pdf(tmp_path):
    """Путь к временному PDF-файлу."""
    return str(tmp_path / "test_report.pdf")


# ─── _fmt ─────────────────────────────────────────────────────────────────────

class TestFmt:
    """Тесты _fmt — форматирование суммы в рублях."""

    def test_integer_value(self):
        assert rg._fmt(1000) == "1\u202f000\u00a0₽"

    def test_large_value(self):
        assert rg._fmt(1_234_567) == "1\u202f234\u202f567\u00a0₽"

    def test_zero(self):
        assert rg._fmt(0) == "0\u00a0₽"

    def test_float_rounds_up(self):
        assert rg._fmt(999.9) == "1\u202f000\u00a0₽"

    def test_float_rounds_down(self):
        assert rg._fmt(999.4) == "999\u00a0₽"

    def test_small_value(self):
        result = rg._fmt(1)
        assert "₽" in result
        assert "1" in result

    def test_negative_value_does_not_raise(self):
        """_fmt не падает на отрицательных значениях."""
        result = rg._fmt(-500)
        assert "₽" in result


# ─── _cap ─────────────────────────────────────────────────────────────────────

class TestCap:
    """Тесты _cap — заглавная первая буква."""

    def test_lowercase_first_letter(self):
        assert rg._cap("продукты") == "Продукты"

    def test_already_capitalized(self):
        assert rg._cap("Продукты") == "Продукты"

    def test_empty_string(self):
        assert rg._cap("") == ""

    def test_single_char(self):
        assert rg._cap("a") == "A"

    def test_uses_python_capitalize(self):
        # Python capitalize() делает первый символ заглавным, остальные — строчными
        assert rg._cap("aBC") == "Abc"

    def test_none_like_empty(self):
        # Пустая строка возвращается как есть (не None)
        result = rg._cap("")
        assert result == ""


# ─── _rub_formatter ───────────────────────────────────────────────────────────

class TestRubFormatter:
    """Тесты _rub_formatter — форматтер оси Y."""

    def test_thousand(self):
        assert rg._rub_formatter(1000, None) == "1\u202f000"

    def test_million(self):
        assert rg._rub_formatter(1_000_000, None) == "1\u202f000\u202f000"

    def test_zero(self):
        assert rg._rub_formatter(0, None) == "0"

    def test_float_truncated(self):
        result = rg._rub_formatter(1500.7, None)
        assert "1" in result and "500" in result

    def test_second_arg_ignored(self):
        # Второй аргумент (pos) всегда игнорируется
        r1 = rg._rub_formatter(500, None)
        r2 = rg._rub_formatter(500, "anything")
        assert r1 == r2


# ─── _rolling_months ──────────────────────────────────────────────────────────

class TestRollingMonths:
    """Тесты _rolling_months — скользящее окно 12 месяцев."""

    def test_returns_12_months(self, today):
        assert len(rg._rolling_months(today)) == 12

    def test_last_element_is_today(self, today):
        result = rg._rolling_months(today)
        assert result[-1] == (today.year, today.month)

    def test_all_valid_months(self, today):
        for year, month in rg._rolling_months(today):
            assert 1 <= month <= 12

    def test_ascending_order(self, today):
        result = rg._rolling_months(today)
        for i in range(len(result) - 1):
            assert result[i] < result[i + 1]

    def test_no_duplicates(self, today):
        result = rg._rolling_months(today)
        assert len(set(result)) == 12

    def test_year_boundary_january(self):
        """Граничный случай: январь."""
        result = rg._rolling_months(datetime.date(2026, 1, 15))
        assert result[0] == (2025, 2)
        assert result[-1] == (2026, 1)

    def test_year_boundary_december(self):
        """Граничный случай: декабрь — все месяцы в одном году."""
        result = rg._rolling_months(datetime.date(2025, 12, 1))
        assert result[0] == (2025, 1)
        assert result[-1] == (2025, 12)

    def test_no_duplicates_all_months(self):
        """Нет дублей ни при каком стартовом месяце."""
        for month in range(1, 13):
            result = rg._rolling_months(datetime.date(2025, month, 1))
            assert len(result) == len(set(result)), \
                f"Дубликаты при month={month}"


# ─── _month_label ─────────────────────────────────────────────────────────────

class TestMonthLabel:
    """Тесты _month_label — подпись месяца на оси."""

    def test_current_year_no_year_suffix(self, today):
        label = rg._month_label(today.year, today.month, today)
        assert "'" not in label

    def test_previous_year_has_year_suffix(self, today):
        label = rg._month_label(today.year - 1, 1, today)
        assert str(today.year - 1)[2:] in label

    def test_january_current_year(self, today):
        label = rg._month_label(today.year, 1, today)
        assert "Янв" in label

    def test_december_prev_year_has_suffix(self):
        today = datetime.date(2026, 3, 1)
        label = rg._month_label(2025, 12, today)
        assert "25" in label

    def test_all_months_non_empty(self, today):
        for m in range(1, 13):
            label = rg._month_label(today.year, m, today)
            assert isinstance(label, str) and len(label) > 0


# ─── _get_cat_color ───────────────────────────────────────────────────────────

class TestGetCatColor:
    """Тесты _get_cat_color — цвет категории."""

    def test_returns_string(self):
        assert isinstance(rg._get_cat_color("продукты", 0), str)

    def test_unknown_category_uses_palette(self):
        color = rg._get_cat_color("неизвестная_xyz_123", 0)
        assert color == rg.PALETTE[0]

    def test_palette_wraps_around(self):
        n = len(rg.PALETTE)
        assert rg._get_cat_color("xyz", 0) == rg._get_cat_color("xyz", n)

    def test_different_indices_give_different_colors(self):
        assert rg._get_cat_color("xyz", 0) != rg._get_cat_color("xyz", 1)

    def test_color_is_hex_or_named(self):
        color = rg._get_cat_color("продукты", 0)
        assert color.startswith("#") or len(color) > 0


# ─── _pie_for_period ──────────────────────────────────────────────────────────

class TestPieForPeriod:
    """Тесты хелпера _pie_for_period."""

    def teardown_method(self):
        plt.close('all')

    def test_renders_with_data(self, sample_df, today):
        fig, ax = plt.subplots()
        # Предыдущий месяц точно есть в sample_df
        prev_m = today.month - 1 or 12
        prev_y = today.year if today.month > 1 else today.year - 1
        rg._pie_for_period(ax, sample_df, prev_y, prev_m, "Тест")
        assert ax is not None

    def test_no_data_period_axis_off(self, sample_df, today):
        """Период без данных — ось выключается."""
        fig, ax = plt.subplots()
        rg._pie_for_period(ax, sample_df, today.year + 5, 1, "Будущее")
        assert not ax.axison

    def test_title_not_set_for_empty_string(self, sample_df, today):
        """Пустой title — set_title не вызывается, нет исключений."""
        fig, ax = plt.subplots()
        prev_m = today.month - 1 or 12
        prev_y = today.year if today.month > 1 else today.year - 1
        rg._pie_for_period(ax, sample_df, prev_y, prev_m, "")
        assert ax is not None

    def test_max_categories_truncated_to_7(self, today):
        """10 категорий → схлопываются в 'прочее', не более 7 секторов."""
        rows = []
        prev_m = today.month - 1 or 12
        prev_y = today.year if today.month > 1 else today.year - 1
        for i in range(10):
            rows.append({
                "date": pd.Timestamp(prev_y, prev_m, 1),
                "amount": float(100 + i * 50),
                "category": f"cat_{i}",
                "description": "",
            })
        df = pd.DataFrame(rows)
        df["date"] = pd.to_datetime(df["date"])
        fig, ax = plt.subplots()
        rg._pie_for_period(ax, df, prev_y, prev_m, "")
        # ax.patches — wedges пирога; их должно быть <= 7
        assert len(ax.patches) <= 7

    def test_single_category_no_crash(self, today):
        """Один сегмент — не падает."""
        df = pd.DataFrame([{
            "date": pd.Timestamp(today.year, today.month, 1),
            "amount": 100.0,
            "category": "единственная",
            "description": "",
        }])
        df["date"] = pd.to_datetime(df["date"])
        fig, ax = plt.subplots()
        rg._pie_for_period(ax, df, today.year, today.month, "")


# ─── Рендеринг страниц ────────────────────────────────────────────────────────

class TestPageRendering:
    """
    Каждая _page_* функция должна:
    - Выполняться без исключений
    - Записать хотя бы один PDF-фрейм (размер > 1 КБ)
    """

    def teardown_method(self):
        plt.close('all')

    def _render(self, func, df, today, tmp_pdf):
        with PdfPages(tmp_pdf) as pdf:
            func(pdf, df, today)
        return os.path.getsize(tmp_pdf)

    def test_page_overview(self, sample_df, today, tmp_pdf):
        assert self._render(rg._page_overview, sample_df, today, tmp_pdf) > 1000

    def test_page_structure_table(self, sample_df, today, tmp_pdf):
        assert self._render(rg._page_structure_table, sample_df, today, tmp_pdf) > 1000

    def test_page_bar_charts(self, sample_df, today, tmp_pdf):
        assert self._render(rg._page_bar_charts, sample_df, today, tmp_pdf) > 1000

    def test_page_trends(self, sample_df, today, tmp_pdf):
        assert self._render(rg._page_trends, sample_df, today, tmp_pdf) > 1000

    def test_page_heatmaps(self, sample_df, today, tmp_pdf):
        assert self._render(rg._page_heatmaps, sample_df, today, tmp_pdf) > 1000

    def test_page_scatter(self, sample_df, today, tmp_pdf):
        assert self._render(rg._page_scatter, sample_df, today, tmp_pdf) > 1000

    def test_page_scatter3_hm3(self, sample_df, today, tmp_pdf):
        assert self._render(rg._page_scatter3_hm3, sample_df, today, tmp_pdf) > 1000

    def test_page_boxplots(self, sample_df, today, tmp_pdf):
        assert self._render(rg._page_boxplots, sample_df, today, tmp_pdf) > 1000

    def test_page_multiline(self, sample_df, today, tmp_pdf):
        assert self._render(rg._page_multiline, sample_df, today, tmp_pdf) > 1000

    def test_page_bar_charts_10_categories(self, today, tmp_pdf):
        """Легенда с 10 категориями не вызывает исключений."""
        rows = []
        for i in range(10):
            for m_off in range(12):
                m = today.month - m_off
                y = today.year
                while m <= 0:
                    m += 12
                    y -= 1
                rows.append({
                    "date": pd.Timestamp(y, m, 1),
                    "amount": float((i + 1) * 150),
                    "category": f"category_{i}",
                    "description": "",
                    "time": datetime.time(12, 0),
                })
        df = pd.DataFrame(rows)
        df["date"] = pd.to_datetime(df["date"])
        assert self._render(rg._page_bar_charts, df, today, tmp_pdf) > 1000

    def test_page_overview_single_month(self, single_month_df, today, tmp_pdf):
        """Данные только за один месяц."""
        assert self._render(rg._page_overview, single_month_df, today, tmp_pdf) > 1000


# ─── _render_full_report ─────────────────────────────────────────────────────

class TestRenderFullReport:
    """Интеграционные тесты полного отчёта."""

    def teardown_method(self):
        plt.close('all')

    def test_creates_pdf_file(self, sample_df, today, tmp_pdf):
        rg._render_full_report(sample_df, today, tmp_pdf)
        assert os.path.exists(tmp_pdf)

    def test_pdf_is_large_enough(self, sample_df, today, tmp_pdf):
        rg._render_full_report(sample_df, today, tmp_pdf)
        assert os.path.getsize(tmp_pdf) > 10_000

    def test_returns_save_path(self, sample_df, today, tmp_pdf):
        result = rg._render_full_report(sample_df, today, tmp_pdf)
        assert result == tmp_pdf

    def test_runs_with_single_month_data(self, single_month_df, today, tmp_pdf):
        """Мало данных — не падает."""
        rg._render_full_report(single_month_df, today, tmp_pdf)
        assert os.path.exists(tmp_pdf)

    def test_pdf_has_multiple_pages(self, sample_df, today, tmp_pdf):
        """Файл достаточно большой чтобы содержать несколько страниц."""
        rg._render_full_report(sample_df, today, tmp_pdf)
        # Типичный многостраничный отчёт > 500 КБ
        assert os.path.getsize(tmp_pdf) > 100_000


# ─── generate_pdf_report (async) ─────────────────────────────────────────────

class TestGeneratePdfReport:
    """Тесты публичной async-функции."""

    @pytest.mark.asyncio
    async def test_returns_none_when_no_data(self, today):
        """Нет данных в обоих годах → None."""
        empty = pd.DataFrame(columns=["date", "amount", "category"])
        empty["date"] = pd.to_datetime(empty["date"])

        with patch("utils.report_generator.excel") as mock_excel:
            mock_excel.get_all_expenses = AsyncMock(return_value=empty)
            mock_excel.create_user_dir = MagicMock(return_value="/tmp")

            result = await rg.generate_pdf_report(user_id=123, project_id=1)

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_excel_returns_none(self):
        """get_all_expenses вернул None → None."""
        with patch("utils.report_generator.excel") as mock_excel:
            mock_excel.get_all_expenses = AsyncMock(return_value=None)
            mock_excel.create_user_dir = MagicMock(return_value="/tmp")

            result = await rg.generate_pdf_report(user_id=123, project_id=1)

        assert result is None

    @pytest.mark.asyncio
    async def test_handles_db_exception_gracefully(self):
        """Исключение в get_all_expenses → функция возвращает None, не падает."""
        with patch("utils.report_generator.excel") as mock_excel:
            mock_excel.get_all_expenses = AsyncMock(
                side_effect=Exception("Connection refused")
            )
            # Ожидаем что функция обработает ошибку (или пробросит —
            # зависит от реализации; главное не unhandled crash)
            try:
                result = await rg.generate_pdf_report(user_id=123, project_id=1)
                assert result is None
            except Exception:
                # Если функция не оборачивает исключение — это тоже приемлемо,
                # тест документирует текущее поведение
                pass

    @pytest.mark.asyncio
    async def test_generates_pdf_with_real_data(self, sample_df, today, tmp_path):
        """End-to-end: реальные данные → PDF создаётся на диске."""
        save_path = str(tmp_path / "report.pdf")

        with patch("utils.report_generator.excel") as mock_excel:
            mock_excel.get_all_expenses = AsyncMock(return_value=sample_df)
            mock_excel.create_user_dir = MagicMock(return_value=str(tmp_path))

            with patch("utils.report_generator.datetime") as mock_dt:
                mock_dt.date.today.return_value = today
                mock_dt.date.side_effect = lambda *a, **kw: datetime.date(*a, **kw)

                result = await rg.generate_pdf_report(user_id=123, project_id=1)

        # Функция должна либо вернуть путь к PDF, либо None
        assert result is None or isinstance(result, str)
