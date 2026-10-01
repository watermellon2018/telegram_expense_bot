"""Currency snapshots and transaction boundaries for recurring operations."""

import asyncio
import copy
import datetime
from contextlib import asynccontextmanager
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from utils import currencies, recurring, recurring_incomes


class RecurringConnection:
    """Minimal transactional store; every SQL operation must use a transaction."""

    def __init__(self, rule_table, operation_table, rule):
        self.rule_table = rule_table
        self.operation_table = operation_table
        self.rule = dict(rule)
        self.role = "editor"
        self.category_available = True
        self.lock = asyncio.Lock()
        self.in_transaction = False
        self.operations = []
        self.new_rules = []
        self.calls = []
        self.row_reads = 0
        self.exists_checks = 0
        self.access_checks = 0
        self.updates = 0
        self.commits = 0
        self.rollbacks = 0
        self.fail_operation_insert = False

    @asynccontextmanager
    async def transaction(self):
        async with self.lock:
            before = copy.deepcopy((self.rule, self.operations, self.new_rules, self.updates))
            self.in_transaction = True
            try:
                yield self
            except BaseException:
                self.rule, self.operations, self.new_rules, self.updates = before
                self.rollbacks += 1
                raise
            else:
                self.commits += 1
            finally:
                self.in_transaction = False

    @asynccontextmanager
    async def acquire(self):
        yield self

    async def fetchrow(self, sql, *args):
        assert self.in_transaction
        assert f"FROM {self.rule_table}" in sql and "FOR UPDATE" in sql
        assert args == (self.rule["id"],)
        self.row_reads += 1
        return dict(self.rule)

    async def fetchval(self, sql, *args):
        assert self.in_transaction
        self.calls.append((sql, args))
        if "SELECT pm.role" in sql:
            assert "FOR SHARE OF p, pm" in sql
            assert "pm.role IN ('owner', 'editor')" in sql
            assert args == (42, "1")
            self.access_checks += 1
            return self.role if self.role in {"owner", "editor"} else None
        if "SELECT EXISTS" in sql:
            assert args == (2, "1", 42)
            return self.category_available
        if f"INSERT INTO {self.rule_table}" in sql:
            self.new_rules.append(args)
            return self.rule["id"]
        assert f"SELECT 1 FROM {self.operation_table}" in sql
        self.exists_checks += 1
        return 1 if self.operations else None

    async def execute(self, sql, *args):
        assert self.in_transaction
        self.calls.append((sql, args))
        if f"INSERT INTO {self.operation_table}" in sql:
            if self.fail_operation_insert:
                raise RuntimeError("operation insert failed")
            await asyncio.sleep(0)
            self.operations.append(args)
            return "INSERT 0 1"
        assert f"UPDATE {self.rule_table} SET next_run_at" in sql
        self.rule["next_run_at"] = args[0]
        self.updates += 1
        return "UPDATE 1"


@pytest.fixture(params=["expense", "income"])
def recurring_case(request, monkeypatch):
    is_income = request.param == "income"
    module = recurring_incomes if is_income else recurring
    category_key = "income_category_id" if is_income else "category_id"
    rule = {
        "id": 77, "user_id": "1", "project_id": 42,
        "amount": Decimal("1500"), "currency": "JPY",
        category_key: 2, "category_name": "Регулярный платёж", "comment": "Оплата",
        "frequency_type": "daily", "interval_value": None, "weekday": None,
        "day_of_month": None, "is_last_day_of_month": False,
        "status": "active", "next_run_at": datetime.datetime.utcnow() - datetime.timedelta(days=1),
    }
    conn = RecurringConnection(
        "recurring_incomes" if is_income else "recurring_rules",
        "incomes" if is_income else "expenses", rule,
    )
    money = {
        "amount": Decimal("1500"), "currency": "JPY",
        "reporting_amount": Decimal("900.00"), "reporting_currency": "RUB",
        "fx_rate": Decimal("0.6"), "fx_date": datetime.datetime.utcnow().date(),
        "fx_source": "cbr",
    }
    prepare = AsyncMock(return_value=money)
    validate = AsyncMock()
    monkeypatch.setattr(module.db, "fetch", AsyncMock(return_value=[rule]))
    monkeypatch.setattr(module.db, "transaction", conn.acquire)
    monkeypatch.setattr(currencies, "prepare_money", prepare)
    monkeypatch.setattr(currencies, "validate_money_context", validate)
    bot = AsyncMock()
    process = module.process_recurring_incomes if is_income else module.process_recurring_expenses

    async def create():
        return await module.create_rule(
            user_id="1", amount=Decimal("1500"), **{category_key: 2},
            comment="Оплата", project_id=42, frequency_type="daily", interval_value=None,
            weekday=None, day_of_month=None, is_last_day_of_month=False,
            start_date=datetime.datetime.utcnow().date(), currency="JPY",
        )

    return conn, rule, money, prepare, validate, bot, process, create


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["create", "process"])
async def test_revoked_editor_cannot_write_after_rate_resolution(recurring_case, action):
    conn, rule, money, prepare, validate, bot, process, create = recurring_case
    previous_date = conn.rule["next_run_at"]

    async def prepare_then_revoke(*args):
        assert not conn.in_transaction
        conn.role = "viewer"
        return money

    prepare.side_effect = prepare_then_revoke
    if action == "create":
        assert await create() is None
    else:
        await process(bot)

    prepare.assert_awaited_once()
    assert conn.access_checks == 1
    assert conn.operations == [] and conn.new_rules == []
    assert conn.rule["next_run_at"] == previous_date
    assert conn.rollbacks == 1 and conn.commits == 0
    bot.send_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_missing_exchange_rate_does_not_advance_schedule(recurring_case):
    conn, rule, money, prepare, validate, bot, process, create = recurring_case
    previous_date = conn.rule["next_run_at"]
    prepare.side_effect = currencies.RateUnavailable("Нет курса")
    await process(bot)
    prepare.assert_awaited_once()
    assert conn.row_reads == 0
    assert conn.operations == []
    assert conn.updates == 0
    assert conn.rule["next_run_at"] == previous_date
    validate.assert_not_awaited()
    bot.send_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_concurrent_schedulers_refresh_locked_rule_before_writing(recurring_case):
    conn, rule, money, prepare, validate, bot, process, create = recurring_case
    both_preparing = asyncio.Event()
    calls = 0

    async def prepare_concurrently(*args):
        nonlocal calls
        assert not conn.in_transaction
        calls += 1
        if calls == 2:
            both_preparing.set()
        await asyncio.wait_for(both_preparing.wait(), timeout=2)
        return money

    prepare.side_effect = prepare_concurrently
    await asyncio.gather(process(bot), process(bot))
    assert prepare.await_count == 2
    assert conn.row_reads == 2
    assert len(conn.operations) == 1
    assert conn.updates == 1
    # The second transaction sees next_run_at moved and never reaches the daily check.
    assert conn.exists_checks == 1
    assert conn.commits == 2 and conn.rollbacks == 0
    bot.send_message.assert_awaited_once()


@pytest.mark.asyncio
async def test_initial_operation_and_rule_rollback_together(recurring_case):
    conn, rule, money, prepare, validate, bot, process, create = recurring_case
    conn.fail_operation_insert = True
    assert await create() is None
    assert any(f"INSERT INTO {conn.rule_table}" in sql for sql, _ in conn.calls)
    assert any(f"INSERT INTO {conn.operation_table}" in sql for sql, _ in conn.calls)
    assert conn.operations == [] and conn.new_rules == []
    assert conn.rollbacks == 1 and conn.commits == 0


@pytest.mark.asyncio
async def test_initial_rule_and_operation_keep_currency_snapshot(recurring_case):
    conn, rule, money, prepare, validate, bot, process, create = recurring_case
    assert await create() == 77
    assert len(conn.new_rules) == len(conn.operations) == 1
    assert conn.new_rules[0][-1] == "JPY"
    assert conn.operations[0][-6:] == (
        "JPY", Decimal("900.00"), "RUB", Decimal("0.6"), money["fx_date"], "cbr",
    )
    assert conn.commits == 1 and conn.rollbacks == 0
    validate.assert_awaited_once_with(conn, "1", 42, money)


@pytest.mark.asyncio
async def test_scheduler_uses_rule_currency_and_keeps_legacy_untyped(recurring_case):
    conn, rule, money, prepare, validate, bot, process, create = recurring_case
    await process(bot)
    prepare.assert_awaited_once_with("1", 42, Decimal("1500"), "JPY", datetime.datetime.utcnow().date())
    assert conn.operations[0][-6:] == (
        "JPY", Decimal("900.00"), "RUB", Decimal("0.6"), money["fx_date"], "cbr",
    )

    # A pre-migration rule has no currency; its next operation must remain untyped.
    conn.operations.clear()
    rule["currency"] = conn.rule["currency"] = None
    conn.rule["next_run_at"] = rule["next_run_at"]
    prepare.reset_mock()
    validate.reset_mock()
    await process(bot)
    prepare.assert_not_awaited()
    validate.assert_not_awaited()
    assert len(conn.operations) == 1
    assert conn.operations[0][-6:] == (None,) * 6
    assert conn.access_checks == 2
