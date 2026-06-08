"""
Форматирование текстов сообщений о расходах для feature_110:
  - предупреждение о возможном дубликате,
  - уведомление участников о новом расходе,
  - детали найденного расхода,
  - уведомление автора об отметке дубликата.

Вынесено отдельно от handlers, чтобы не держать форматирование в обработчиках.
"""

import datetime
from typing import Optional

# Месяцы в родительном падеже для дат вида «8 июня 2026»
_MONTHS_GENITIVE = [
    "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
]


def format_date_human(d: Optional[datetime.date]) -> str:
    """«8 июня 2026»."""
    if d is None:
        return "—"
    return f"{d.day} {_MONTHS_GENITIVE[d.month - 1]} {d.year}"


def format_datetime_human(dt: Optional[datetime.datetime]) -> str:
    """«8 июня 2026, 10:15»."""
    if dt is None:
        return "—"
    return f"{format_date_human(dt.date())}, {dt.strftime('%H:%M')}"


def format_amount(amount) -> str:
    """Форматирует сумму с разделителем тысяч: 1250 → «1 250»."""
    try:
        value = float(amount)
    except (TypeError, ValueError):
        return str(amount)
    # Целые показываем без дробной части, иначе с двумя знаками
    if value == int(value):
        text = f"{int(value):,}".replace(",", " ")
    else:
        text = f"{value:,.2f}".replace(",", " ")
    return text


def format_relative_time(created_at: Optional[datetime.datetime],
                         now: Optional[datetime.datetime] = None) -> str:
    """Относительное время: «7 минут назад», «2 часа назад», «только что»."""
    if created_at is None:
        return "—"
    now = now or datetime.datetime.now()
    delta = now - created_at
    seconds = int(delta.total_seconds())
    if seconds < 0:
        seconds = 0

    if seconds < 60:
        return "только что"

    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes} {_plural(minutes, 'минуту', 'минуты', 'минут')} назад"

    hours = minutes // 60
    if hours < 24:
        return f"{hours} {_plural(hours, 'час', 'часа', 'часов')} назад"

    days = hours // 24
    return f"{days} {_plural(days, 'день', 'дня', 'дней')} назад"


def _plural(n: int, one: str, few: str, many: str) -> str:
    """Русское склонение по числу."""
    if 11 <= n % 100 <= 14:
        return many
    r = n % 10
    if r == 1:
        return one
    if 2 <= r <= 4:
        return few
    return many


def _author_display(author_id: str, author_name: Optional[str]) -> str:
    """Имя автора или fallback на ID."""
    if author_name:
        return author_name
    return f"ID: {author_id}"


def format_duplicate_warning(existing: dict, author_name: Optional[str] = None,
                             now: Optional[datetime.datetime] = None) -> str:
    """
    Текст предупреждения о возможном дубликате.

    existing — dict с полями расхода (amount, category_name, author_id,
    description, date, created_at).
    """
    lines = ["⚠️ Возможно, этот расход уже добавлен", ""]

    title = existing.get("description") or existing.get("category_name", "Расход")
    lines.append(f"{title} — {format_amount(existing['amount'])} ₽")
    lines.append(f"Категория: {existing.get('category_name', '—')}")
    lines.append(f"Добавил: {_author_display(existing.get('author_id', ''), author_name)}")
    lines.append(f"Дата расхода: {format_date_human(existing.get('date'))}")
    lines.append(f"Добавлен: {format_relative_time(existing.get('created_at'), now)}")
    lines.append("")
    lines.append("Вы всё равно хотите добавить новый расход?")
    return "\n".join(lines)


def format_expense_details(expense: dict, author_name: Optional[str] = None) -> str:
    """Подробности расхода (для кнопки «Посмотреть расход»)."""
    lines = ["👁 Детали расхода", ""]
    title = expense.get("description") or expense.get("category_name", "Расход")
    lines.append(f"{title} — {format_amount(expense['amount'])} ₽")
    lines.append(f"Категория: {expense.get('category_name', '—')}")
    lines.append(f"Добавил: {_author_display(expense.get('author_id') or expense.get('user_id', ''), author_name)}")
    lines.append(f"Дата расхода: {format_date_human(expense.get('date'))}")
    created = expense.get("created_at")
    if created is not None:
        lines.append(f"Добавлен: {format_datetime_human(created)}")
    if expense.get("description"):
        lines.append(f"Комментарий: {expense['description']}")
    return "\n".join(lines)


def format_expense_notification(project_name: str, expense: dict,
                                author_name: Optional[str] = None) -> str:
    """
    Уведомление участникам о новом расходе.

    Поля без значения (например, комментарий) не отображаются.
    """
    lines = [f"💸 В проект «{project_name}» добавлен расход", ""]

    title = expense.get("description") or expense.get("category_name", "Расход")
    lines.append(f"{title} — {format_amount(expense['amount'])} ₽")
    lines.append(f"Категория: {expense.get('category_name', '—')}")
    lines.append(f"Добавил: {_author_display(expense.get('author_id') or expense.get('user_id', ''), author_name)}")

    created = expense.get("created_at")
    if created is not None:
        lines.append(f"Дата: {format_datetime_human(created)}")
    else:
        lines.append(f"Дата: {format_date_human(expense.get('date'))}")

    # Комментарий — только если есть
    if expense.get("description"):
        lines.append(f"Комментарий: {expense['description']}")

    return "\n".join(lines)


def format_duplicate_report_to_author(project_name: str, expense: dict,
                                      reporter_name: Optional[str] = None) -> str:
    """Уведомление автора расхода о том, что его пометили как возможный дубликат."""
    lines = ["⚠️ Участник проекта считает расход возможным дубликатом", ""]
    title = expense.get("description") or expense.get("category_name", "Расход")
    lines.append(f"{title} — {format_amount(expense['amount'])} ₽")
    lines.append(f"Проект: {project_name}")
    reporter = reporter_name or "участник"
    lines.append(f"Отметил: {reporter}")
    return "\n".join(lines)
