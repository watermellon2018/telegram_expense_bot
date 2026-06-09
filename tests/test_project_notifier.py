"""
Тесты сервиса уведомлений участников проекта (feature_110).

Покрывают обязательные сценарии ТЗ:
 10. Уведомление получает каждый подходящий участник, кроме автора.
 11. Участник с режимом DISABLED не получает уведомление.
 12. Участник с режимом LARGE_ONLY получает только расходы выше порога.
 13. Ошибка Telegram у одного получателя не мешает остальным.
"""

import datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import config
from utils import project_notifier


def _expense(amount=1000, author="111", project_id=1):
    return {
        "id": 10,
        "user_id": author,
        "project_id": project_id,
        "amount": Decimal(str(amount)),
        "category_id": 5,
        "category_name": "Кафе и рестораны",
        "description": "Завтрак",
        "date": datetime.date.today(),
        "time": datetime.time(10, 0),
        "created_at": datetime.datetime.now(),
        "deleted_at": None,
    }


def _settings(mode=config.ExpenseNotifyMode.ALL, threshold=None):
    return {
        "project_id": 1, "user_id": "x",
        "expense_notify_mode": mode,
        "large_expense_threshold": threshold,
        "updated_at": None,
    }


class FakeBot:
    def __init__(self, fail_for=None):
        self.sent = []
        self.fail_for = fail_for or set()

    async def send_message(self, chat_id, text, reply_markup=None):
        if chat_id in self.fail_for:
            raise RuntimeError(f"send failed for {chat_id}")
        self.sent.append(chat_id)

    async def get_chat(self, uid):
        m = MagicMock()
        m.first_name = f"User{uid}"
        m.username = None
        return m


# --- helper for _should_notify ---

def test_should_notify_all():
    assert project_notifier._should_notify(_settings(config.ExpenseNotifyMode.ALL), Decimal("10"))


def test_should_notify_disabled():
    assert not project_notifier._should_notify(
        _settings(config.ExpenseNotifyMode.DISABLED), Decimal("10000"))


def test_should_notify_large_only_above_threshold():
    s = _settings(config.ExpenseNotifyMode.LARGE_ONLY, threshold=Decimal("500"))
    assert project_notifier._should_notify(s, Decimal("1000"))


def test_should_notify_large_only_below_threshold():
    s = _settings(config.ExpenseNotifyMode.LARGE_ONLY, threshold=Decimal("500"))
    assert not project_notifier._should_notify(s, Decimal("100"))


def test_should_notify_large_only_no_threshold_defaults_true():
    s = _settings(config.ExpenseNotifyMode.LARGE_ONLY, threshold=None)
    assert project_notifier._should_notify(s, Decimal("100"))


# --- Сценарий 10: уведомляются все подходящие, кроме автора ---

@pytest.mark.asyncio
async def test_notify_excludes_author_and_sends_to_others():
    bot = FakeBot()
    members = [
        {"user_id": "111", "role": "owner"},   # автор
        {"user_id": "222", "role": "editor"},
        {"user_id": "333", "role": "viewer"},
    ]
    with patch("utils.project_notifier.excel.get_expense_by_id", new=AsyncMock(return_value=_expense(author="111"))), \
         patch("utils.project_notifier.projects.get_project_by_id", new=AsyncMock(return_value={"project_name": "Стамбул"})), \
         patch("utils.project_notifier.projects.get_project_members", new=AsyncMock(return_value=members)), \
         patch("utils.project_notifier.has_permission", new=AsyncMock(return_value=True)), \
         patch("utils.project_notifier.project_notifications.get_member_settings",
               new=AsyncMock(return_value=_settings(config.ExpenseNotifyMode.ALL))):
        stats = await project_notifier.notify_expense_created(bot, expense_id=10, author_id=111)

    assert stats["sent"] == 2
    assert 111 not in bot.sent       # автор не уведомлён
    assert set(bot.sent) == {222, 333}


# --- Сценарий 11: DISABLED не получает ---

@pytest.mark.asyncio
async def test_notify_skips_disabled_member():
    bot = FakeBot()
    members = [
        {"user_id": "111", "role": "owner"},   # автор
        {"user_id": "222", "role": "editor"},
    ]

    async def settings_for(project_id, uid):
        if uid == 222:
            return _settings(config.ExpenseNotifyMode.DISABLED)
        return _settings(config.ExpenseNotifyMode.ALL)

    with patch("utils.project_notifier.excel.get_expense_by_id", new=AsyncMock(return_value=_expense(author="111"))), \
         patch("utils.project_notifier.projects.get_project_by_id", new=AsyncMock(return_value={"project_name": "P"})), \
         patch("utils.project_notifier.projects.get_project_members", new=AsyncMock(return_value=members)), \
         patch("utils.project_notifier.has_permission", new=AsyncMock(return_value=True)), \
         patch("utils.project_notifier.project_notifications.get_member_settings", new=settings_for):
        stats = await project_notifier.notify_expense_created(bot, expense_id=10, author_id=111)

    assert 222 not in bot.sent
    assert stats["sent"] == 0
    assert stats["skipped"] == 1


# --- Сценарий 12: LARGE_ONLY получает только крупные ---

@pytest.mark.asyncio
async def test_notify_large_only_below_threshold_skipped():
    bot = FakeBot()
    members = [
        {"user_id": "111", "role": "owner"},   # автор
        {"user_id": "222", "role": "editor"},
    ]
    # Расход 100, порог участника 500 → не уведомляем
    with patch("utils.project_notifier.excel.get_expense_by_id", new=AsyncMock(return_value=_expense(amount=100, author="111"))), \
         patch("utils.project_notifier.projects.get_project_by_id", new=AsyncMock(return_value={"project_name": "P"})), \
         patch("utils.project_notifier.projects.get_project_members", new=AsyncMock(return_value=members)), \
         patch("utils.project_notifier.has_permission", new=AsyncMock(return_value=True)), \
         patch("utils.project_notifier.project_notifications.get_member_settings",
               new=AsyncMock(return_value=_settings(config.ExpenseNotifyMode.LARGE_ONLY, threshold=Decimal("500")))):
        stats = await project_notifier.notify_expense_created(bot, expense_id=10, author_id=111)

    assert 222 not in bot.sent
    assert stats["sent"] == 0


@pytest.mark.asyncio
async def test_notify_large_only_above_threshold_sent():
    bot = FakeBot()
    members = [
        {"user_id": "111", "role": "owner"},   # автор
        {"user_id": "222", "role": "editor"},
    ]
    with patch("utils.project_notifier.excel.get_expense_by_id", new=AsyncMock(return_value=_expense(amount=1000, author="111"))), \
         patch("utils.project_notifier.projects.get_project_by_id", new=AsyncMock(return_value={"project_name": "P"})), \
         patch("utils.project_notifier.projects.get_project_members", new=AsyncMock(return_value=members)), \
         patch("utils.project_notifier.has_permission", new=AsyncMock(return_value=True)), \
         patch("utils.project_notifier.project_notifications.get_member_settings",
               new=AsyncMock(return_value=_settings(config.ExpenseNotifyMode.LARGE_ONLY, threshold=Decimal("500")))):
        stats = await project_notifier.notify_expense_created(bot, expense_id=10, author_id=111)

    assert 222 in bot.sent
    assert stats["sent"] == 1


# --- viewer без права просмотра не уведомляется ---

@pytest.mark.asyncio
async def test_notify_skips_member_without_view_permission():
    bot = FakeBot()
    members = [
        {"user_id": "111", "role": "owner"},
        {"user_id": "222", "role": "viewer"},
    ]

    async def perm(uid, pid, permission):
        return uid != 222  # 222 без права просмотра

    with patch("utils.project_notifier.excel.get_expense_by_id", new=AsyncMock(return_value=_expense(author="111"))), \
         patch("utils.project_notifier.projects.get_project_by_id", new=AsyncMock(return_value={"project_name": "P"})), \
         patch("utils.project_notifier.projects.get_project_members", new=AsyncMock(return_value=members)), \
         patch("utils.project_notifier.has_permission", new=perm), \
         patch("utils.project_notifier.project_notifications.get_member_settings",
               new=AsyncMock(return_value=_settings(config.ExpenseNotifyMode.ALL))):
        stats = await project_notifier.notify_expense_created(bot, expense_id=10, author_id=111)

    assert 222 not in bot.sent
    assert stats["skipped"] == 1


# --- Сценарий 13: ошибка у одного получателя не мешает остальным ---

@pytest.mark.asyncio
async def test_notify_error_for_one_does_not_block_others():
    bot = FakeBot(fail_for={222})
    members = [
        {"user_id": "111", "role": "owner"},   # автор
        {"user_id": "222", "role": "editor"},  # упадёт
        {"user_id": "333", "role": "editor"},  # должен получить
    ]
    with patch("utils.project_notifier.excel.get_expense_by_id", new=AsyncMock(return_value=_expense(author="111"))), \
         patch("utils.project_notifier.projects.get_project_by_id", new=AsyncMock(return_value={"project_name": "P"})), \
         patch("utils.project_notifier.projects.get_project_members", new=AsyncMock(return_value=members)), \
         patch("utils.project_notifier.has_permission", new=AsyncMock(return_value=True)), \
         patch("utils.project_notifier.project_notifications.get_member_settings",
               new=AsyncMock(return_value=_settings(config.ExpenseNotifyMode.ALL))):
        stats = await project_notifier.notify_expense_created(bot, expense_id=10, author_id=111)

    assert 333 in bot.sent          # остальные получили несмотря на ошибку
    assert stats["sent"] == 1
    assert stats["failed"] == 1


@pytest.mark.asyncio
async def test_notify_personal_expense_no_recipients():
    """Личный расход (project_id=None) — никого не уведомляем."""
    bot = FakeBot()
    exp = _expense(author="111", project_id=None)
    with patch("utils.project_notifier.excel.get_expense_by_id", new=AsyncMock(return_value=exp)):
        stats = await project_notifier.notify_expense_created(bot, expense_id=10, author_id=111)
    assert stats["sent"] == 0
    assert bot.sent == []
