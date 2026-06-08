"""Тесты форматирования сообщений feature_110."""

import datetime

from utils import expense_formatter as f


def test_format_amount_integer():
    assert f.format_amount(1250) == "1 250"


def test_format_amount_float():
    assert f.format_amount(1250.5) == "1 250.50"


def test_format_date_human():
    assert f.format_date_human(datetime.date(2026, 6, 8)) == "8 июня 2026"


def test_format_datetime_human():
    dt = datetime.datetime(2026, 6, 8, 10, 15)
    assert f.format_datetime_human(dt) == "8 июня 2026, 10:15"


def test_relative_time_minutes():
    now = datetime.datetime(2026, 6, 8, 10, 15)
    assert f.format_relative_time(now - datetime.timedelta(minutes=7), now) == "7 минут назад"
    assert f.format_relative_time(now - datetime.timedelta(minutes=1), now) == "1 минуту назад"


def test_relative_time_hours():
    now = datetime.datetime(2026, 6, 8, 10, 15)
    assert f.format_relative_time(now - datetime.timedelta(hours=2), now) == "2 часа назад"


def test_relative_time_just_now():
    now = datetime.datetime(2026, 6, 8, 10, 15)
    assert f.format_relative_time(now - datetime.timedelta(seconds=10), now) == "только что"


def test_duplicate_warning_contains_required_fields():
    existing = {
        "id": 1, "amount": 1250, "category_name": "Кафе и рестораны",
        "author_id": "999", "description": "Завтрак",
        "date": datetime.date(2026, 6, 8),
        "created_at": datetime.datetime(2026, 6, 8, 10, 8),
    }
    now = datetime.datetime(2026, 6, 8, 10, 15)
    text = f.format_duplicate_warning(existing, author_name="Анна", now=now)
    assert "Возможно, этот расход уже добавлен" in text
    assert "Завтрак — 1 250 ₽" in text
    assert "Категория: Кафе и рестораны" in text
    assert "Добавил: Анна" in text
    assert "Дата расхода: 8 июня 2026" in text
    assert "7 минут назад" in text


def test_notification_omits_empty_comment():
    expense = {
        "id": 1, "amount": 1250, "category_name": "Кафе и рестораны",
        "user_id": "999", "description": None,
        "date": datetime.date(2026, 6, 8),
        "created_at": datetime.datetime(2026, 6, 8, 10, 15),
    }
    text = f.format_expense_notification("Поездка в Стамбул", expense, author_name="Екатерина")
    assert "В проект «Поездка в Стамбул» добавлен расход" in text
    assert "Комментарий" not in text  # пустой комментарий не показывается


def test_notification_includes_comment_when_present():
    expense = {
        "id": 1, "amount": 1250, "category_name": "Кафе и рестораны",
        "user_id": "999", "description": "Завтрак в отеле",
        "date": datetime.date(2026, 6, 8),
        "created_at": datetime.datetime(2026, 6, 8, 10, 15),
    }
    text = f.format_expense_notification("Поездка в Стамбул", expense, author_name="Екатерина")
    assert "Комментарий: Завтрак в отеле" in text


def test_author_fallback_to_id():
    existing = {
        "id": 1, "amount": 100, "category_name": "кафе",
        "author_id": "999", "description": "",
        "date": datetime.date(2026, 6, 8),
        "created_at": datetime.datetime(2026, 6, 8, 10, 8),
    }
    text = f.format_duplicate_warning(existing, author_name=None)
    assert "ID: 999" in text
