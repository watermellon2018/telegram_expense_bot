"""Currency settings and immutable monetary snapshots for personal/project accounts."""

from __future__ import annotations

from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

from utils import db
from utils.permissions import Permission, require_permission

CURRENCIES = {
    "RUB": {"name": "Российский рубль", "symbol": "₽", "decimals": 2},
    "USD": {"name": "Доллар США", "symbol": "$", "decimals": 2},
    "EUR": {"name": "Евро", "symbol": "€", "decimals": 2},
    "JPY": {"name": "Японская иена", "symbol": "¥", "decimals": 0},
    "CNY": {"name": "Китайский юань", "symbol": "¥", "decimals": 2},
    "THB": {"name": "Тайский бат", "symbol": "฿", "decimals": 2},
    "AED": {"name": "Дирхам ОАЭ", "symbol": "د.إ", "decimals": 2},
    "TRY": {"name": "Турецкая лира", "symbol": "₺", "decimals": 2},
    "GBP": {"name": "Британский фунт", "symbol": "£", "decimals": 2},
    "KZT": {"name": "Казахстанский тенге", "symbol": "₸", "decimals": 2},
    "GEL": {"name": "Грузинский лари", "symbol": "₾", "decimals": 2},
    "KRW": {"name": "Южнокорейская вона", "symbol": "₩", "decimals": 0},
}


class CurrencyError(ValueError):
    """A user-correctable currency or money validation error."""


class RateUnavailable(CurrencyError):
    """Neither an automatic nor a context-specific manual rate is available."""


def normalize_currency(code: str) -> str:
    code = str(code).strip().upper()
    if code not in CURRENCIES:
        raise CurrencyError("Неизвестная валюта. Выберите валюту из списка.")
    return code


def parse_amount(value: Any) -> Decimal:
    try:
        amount = Decimal(str(value).replace(" ", "").replace(",", "."))
    except (InvalidOperation, ValueError):
        raise CurrencyError("Введите положительную сумму числом.") from None
    if not amount.is_finite() or amount <= 0 or amount > Decimal("999999999999"):
        raise CurrencyError("Сумма должна быть положительной и меньше 1 триллиона.")
    return amount


def round_money(amount: Decimal, code: str) -> Decimal:
    code = normalize_currency(code)
    try:
        return amount.quantize(Decimal(1).scaleb(-CURRENCIES[code]["decimals"]), rounding=ROUND_HALF_UP)
    except InvalidOperation:
        raise CurrencyError("Сумма слишком велика.") from None


def format_money(amount: Any, code: str | None) -> str:
    if code is None:
        return f"{Decimal(str(amount)):,.2f}".replace(",", " ") + " (без валюты)"
    code = normalize_currency(code)
    rounded = round_money(Decimal(str(amount)), code)
    return f"{rounded:,.{CURRENCIES[code]['decimals']}f}".replace(",", " ") + f" {code}"


async def _context(conn: Any, user_id: int, project_id: int | None, *, lock: bool = False,
                   owner: bool = False, writer: bool = False) -> str:
    """Read/lock the account and check live membership within the same transaction."""
    if project_id is None:
        row = await conn.fetchrow(
            "SELECT reporting_currency FROM users WHERE user_id=$1" + (" FOR UPDATE" if lock else ""),
            str(user_id),
        )
    else:
        row = await conn.fetchrow(
            """SELECT p.reporting_currency, pm.role FROM projects p
               JOIN project_members pm ON pm.project_id=p.project_id AND pm.user_id=$1
               WHERE p.project_id=$2 AND p.deleted_at IS NULL"""
            + (" FOR UPDATE OF p, pm" if lock else ""), str(user_id), project_id,
        )
        if row and owner and row["role"] != "owner":
            raise PermissionError("Валюту отчётности и резервные курсы меняет владелец проекта.")
        if row and writer and row["role"] not in ("owner", "editor"):
            raise PermissionError("Нет прав на изменение денежных данных проекта.")
    if not row:
        raise CurrencyError("Личный учёт или проект недоступен.")
    return normalize_currency(row["reporting_currency"])


async def get_reporting_currency(user_id: int, project_id: int | None = None) -> str:
    await require_permission(user_id, project_id, Permission.VIEW_STATS)
    if project_id is None:
        await db.execute("INSERT INTO users(user_id) VALUES($1) ON CONFLICT DO NOTHING", str(user_id))
    return await _context(db, user_id, project_id)


async def get_input_currency(user_id: int, project_id: int | None = None) -> str:
    reporting = await get_reporting_currency(user_id, project_id)
    value = await db.fetchval(
        "SELECT currency FROM currency_preferences WHERE user_id=$1 AND project_id IS NOT DISTINCT FROM $2",
        str(user_id), project_id,
    )
    return normalize_currency(value) if value else reporting


async def set_input_currency(user_id: int, project_id: int | None, code: str) -> None:
    code = normalize_currency(code)
    await require_permission(user_id, project_id, Permission.VIEW_STATS)
    async with db.transaction() as conn:
        async with conn.transaction():
            await _context(conn, user_id, project_id, lock=True)
            await conn.execute(
                """INSERT INTO currency_preferences(user_id,project_id,currency) VALUES($1,$2,$3)
                   ON CONFLICT (user_id,(COALESCE(project_id,0))) DO UPDATE SET currency=EXCLUDED.currency""",
                str(user_id), project_id, code,
            )


async def set_reporting_currency(user_id: int, project_id: int | None, code: str) -> None:
    code = normalize_currency(code)
    await require_permission(user_id, project_id, Permission.DELETE_PROJECT)
    async with db.transaction() as conn:
        async with conn.transaction():
            previous = await _context(conn, user_id, project_id, lock=True, owner=True)
            if previous == code:
                return
            # Every new money writer must take this same account lock before insertion.
            occupied = await conn.fetchval(
                """SELECT EXISTS (
                    SELECT 1 FROM expenses WHERE currency IS NOT NULL AND
                        (($2::integer IS NULL AND project_id IS NULL AND user_id=$1) OR project_id=$2)
                    UNION ALL SELECT 1 FROM incomes WHERE currency IS NOT NULL AND
                        (($2 IS NULL AND project_id IS NULL AND user_id=$1) OR project_id=$2)
                    UNION ALL SELECT 1 FROM budgets WHERE currency IS NOT NULL AND
                        (($2 IS NULL AND project_id IS NULL AND user_id=$1) OR project_id=$2)
                    UNION ALL SELECT 1 FROM recurring_rules WHERE currency IS NOT NULL AND
                        (($2 IS NULL AND project_id IS NULL AND user_id=$1) OR project_id=$2)
                    UNION ALL SELECT 1 FROM recurring_incomes WHERE currency IS NOT NULL AND
                        (($2 IS NULL AND project_id IS NULL AND user_id=$1) OR project_id=$2)
                    UNION ALL SELECT 1 FROM project_member_settings
                        WHERE threshold_currency IS NOT NULL AND project_id=$2
                    UNION ALL SELECT 1 FROM cashback_monthly_snapshots
                        WHERE currency IS NOT NULL AND $2 IS NULL AND user_id=$1
                )""", str(user_id), project_id,
            )
            if occupied:
                raise CurrencyError("Валюту отчётности нельзя изменить после появления операций или денежных настроек с валютой.")
            if project_id is None:
                await conn.execute("UPDATE users SET reporting_currency=$2 WHERE user_id=$1", str(user_id), code)
            else:
                await conn.execute("UPDATE projects SET reporting_currency=$2 WHERE project_id=$1", project_id, code)


async def get_fallback_rate(user_id: int, project_id: int | None, source_currency: str,
                            target_currency: str | None = None) -> Decimal | None:
    reporting = await get_reporting_currency(user_id, project_id)
    target = normalize_currency(target_currency or reporting)
    return await db.fetchval(
        """SELECT rate FROM currency_fallback_rates WHERE
           ((project_id=$2) OR ($2::integer IS NULL AND project_id IS NULL AND user_id=$1))
           AND source_currency=$3 AND target_currency=$4""",
        str(user_id), project_id, normalize_currency(source_currency), target,
    )


async def set_fallback_rate(user_id: int, project_id: int | None, source_currency: str, rate: Any) -> None:
    source = normalize_currency(source_currency)
    rate = parse_amount(rate)
    await require_permission(user_id, project_id, Permission.DELETE_PROJECT)
    async with db.transaction() as conn:
        async with conn.transaction():
            target = await _context(conn, user_id, project_id, lock=True, owner=True)
            if source == target:
                raise CurrencyError("Для одинаковых валют курс всегда равен 1.")
            await conn.execute(
                """INSERT INTO currency_fallback_rates(user_id,project_id,source_currency,target_currency,rate)
                   VALUES($1,$2,$3,$4,$5)
                   ON CONFLICT ((COALESCE(project_id,0)),(CASE WHEN project_id IS NULL THEN user_id ELSE '' END),
                                source_currency,target_currency)
                   DO UPDATE SET rate=EXCLUDED.rate, updated_at=now()""",
                str(user_id), project_id, source, target, rate,
            )


async def get_settings(user_id: int, project_id: int | None = None) -> dict:
    reporting = await get_reporting_currency(user_id, project_id)
    rows = await db.fetch(
        """SELECT source_currency,rate FROM currency_fallback_rates WHERE target_currency=$3 AND
           (project_id=$2 OR ($2::integer IS NULL AND project_id IS NULL AND user_id=$1))""",
        str(user_id), project_id, reporting,
    )
    return {"reporting_currency": reporting, "input_currency": await get_input_currency(user_id, project_id),
            "fallback_rates": {row["source_currency"]: row["rate"] for row in rows}}


async def prepare_money(user_id: int, project_id: int | None, amount: Any, currency: str | None = None,
                        operation_date: date | None = None) -> dict:
    from utils.currency_rates import get_rate

    await require_permission(user_id, project_id, Permission.ADD_EXPENSE)
    amount = parse_amount(amount)
    target = await get_reporting_currency(user_id, project_id)
    source = normalize_currency(currency) if currency else await get_input_currency(user_id, project_id)
    rounded = round_money(amount, source)
    if rounded != amount:
        raise CurrencyError(f"У валюты {source} допустимо знаков после запятой: {CURRENCIES[source]['decimals']}.")
    requested = operation_date or date.today()
    if isinstance(requested, datetime):
        requested = requested.date()
    if not isinstance(requested, date) or requested > date.today():
        raise CurrencyError("Для пересчёта нужна дата не позднее сегодняшней.")
    rate, effective, origin = Decimal(1), requested, "identity"
    if source != target:
        try:
            rate, effective = await get_rate(source, target, requested)
            origin = "cbr"
        except RateUnavailable:
            rate = await get_fallback_rate(user_id, project_id, source, target)
            if rate is None:
                raise RateUnavailable(f"Курс {source} → {target} недоступен. Задайте резервный курс.") from None
            rate, origin = parse_amount(rate), "manual"
    converted = round_money(amount * rate, target)
    if converted > Decimal("999999999999"):
        raise CurrencyError("Сумма после пересчёта слишком велика.")
    return {"amount": rounded, "currency": source, "reporting_amount": converted, "operation_date": requested,
            "reporting_currency": target, "fx_rate": rate, "fx_date": effective, "fx_source": origin}


async def validate_money_context(conn: Any, user_id: int, project_id: int | None, money: dict,
                                 *, writer: bool = False) -> None:
    """Serialize against account currency changes; caller owns the SQL transaction."""
    target = await _context(conn, user_id, project_id, lock=True, writer=writer)
    if target != money["reporting_currency"]:
        raise CurrencyError("Валюта отчётности изменилась. Повторите добавление операции.")
