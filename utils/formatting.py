"""Formatting helpers for user-facing reports."""

import datetime


def get_month_name(month: int) -> str:
    """Return localized month name by month number (1-12)."""
    months = [
        "Январь",
        "Февраль",
        "Март",
        "Апрель",
        "Май",
        "Июнь",
        "Июль",
        "Август",
        "Сентябрь",
        "Октябрь",
        "Ноябрь",
        "Декабрь",
    ]
    return months[month - 1]


def format_month_expenses(expenses, month=None, year=None):
    """Format month expense statistics into a Telegram message."""
    if month is None:
        month = datetime.datetime.now().month
    if year is None:
        year = datetime.datetime.now().year

    month_name = get_month_name(month)

    if not expenses or expenses["total"] == 0:
        return f"В {month_name} {year} года расходов не было."

    report = f"📊 Статистика расходов за {month_name} {year} года:\n\n"
    report += f"💰 Общая сумма: {expenses['total']:.2f}\n"
    report += f"🧾 Количество транзакций: {expenses['count']}\n\n"

    by_participant = expenses.get("by_participant", {}) if expenses else {}
    if by_participant:
        report += "👥 По участникам:\n"
        sorted_participants = sorted(
            by_participant.items(),
            key=lambda x: x[1],
            reverse=True,
        )
        for participant_name, amount in sorted_participants:
            report += f"- {participant_name}: {amount:.2f}\n"
        report += "\n"

    report += "📋 Расходы по категориям:\n"
    sorted_categories = sorted(
        expenses["by_category"].items(),
        key=lambda x: x[1],
        reverse=True,
    )

    from config import DEFAULT_CATEGORIES

    for category, amount in sorted_categories:
        emoji = DEFAULT_CATEGORIES.get(category, "📦")
        report += f"{emoji} {category.title()}: {amount:.2f}\n"

    return report


def format_category_expenses(category_data, category, year=None):
    """Format yearly category statistics into a Telegram message."""
    if year is None:
        year = datetime.datetime.now().year

    if not category_data or category_data["total"] == 0:
        return f"В {year} году расходов по категории '{category}' не было."

    from config import DEFAULT_CATEGORIES

    emoji = DEFAULT_CATEGORIES.get(category.lower(), "📦")
    report = f"📊 Статистика расходов по категории {emoji} {category} за {year} год:\n\n"
    report += f"💰 Общая сумма: {category_data['total']:.2f}\n"
    report += f"🧾 Количество транзакций: {category_data['count']}\n\n"
    report += "📅 Расходы по месяцам:\n"

    for month in range(1, 13):
        month_name = get_month_name(month)
        amount = category_data["by_month"].get(month, 0)
        report += f"{month_name}: {amount:.2f}\n"

    return report


def format_day_expenses(expenses, date=None):
    """Format daily expense statistics into a Telegram message."""
    if date is None:
        date = datetime.datetime.now().strftime("%Y-%m-%d")

    if not expenses or expenses["total"] == 0:
        return f"Расходов за {date} не было."

    report = f"📊 Статистика расходов за {date}:\n\n"
    report += f"💰 Общая сумма: {expenses['total']:.2f}\n"
    report += f"🧾 Количество транзакций: {expenses['count']}\n\n"

    by_participant = expenses.get("by_participant", {}) if expenses else {}
    if by_participant:
        report += "👥 По участникам:\n"
        sorted_participants = sorted(
            by_participant.items(),
            key=lambda x: x[1],
            reverse=True,
        )
        for participant_name, amount in sorted_participants:
            report += f"- {participant_name}: {amount:.2f}\n"
        report += "\n"

    report += "📋 Расходы по категориям:\n"
    sorted_categories = sorted(
        expenses["by_category"].items(),
        key=lambda x: x[1],
        reverse=True,
    )

    from config import DEFAULT_CATEGORIES

    for category, amount in sorted_categories:
        emoji = DEFAULT_CATEGORIES.get(category, "📦")
        percentage = (amount / expenses["total"]) * 100
        report += f"{emoji} {category.title()}: {amount:.2f} ({percentage:.1f}%)\n"

    return report


async def format_budget_status(user_id, month=None, year=None):
    """Budget status is disabled in current product iteration."""
    if month is None:
        month = datetime.datetime.now().month
    if year is None:
        year = datetime.datetime.now().year
    return "📊 Функция бюджета отключена."


async def add_project_context_to_report(report: str, user_id: int, project_id: int = None) -> str:
    """Prefix report with current project context."""
    if project_id is not None:
        from utils import projects

        project = await projects.get_project_by_id(user_id, project_id)
        if project:
            return f"📁 Проект: {project['project_name']}\n\n{report}"

    return f"📊 Общие расходы\n\n{report}"
