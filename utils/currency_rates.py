"""Daily CBR rates, shared persistent cache and bounded concurrent fetching."""

from __future__ import annotations

import asyncio
import json
import time
from collections import OrderedDict
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from xml.etree import ElementTree

import httpx

from utils import db
from utils.currencies import CURRENCIES, RateUnavailable, normalize_currency

_inflight: dict[date, asyncio.Task] = {}
_failures: OrderedDict[date, float] = OrderedDict()
_memory: OrderedDict[date, tuple[date, dict[str, Decimal]]] = OrderedDict()
_CACHE_LIMIT = 256
_RETRY_SECONDS = 60


def parse_cbr_xml(content: bytes, requested: date) -> tuple[date, dict[str, Decimal]]:
    """Normalize nominal quotes (e.g. 100 JPY) to RUB for one currency unit."""
    try:
        if len(content) > 1_000_000 or b"<!DOCTYPE" in content.upper() or b"<!ENTITY" in content.upper():
            raise ValueError("Unsupported XML")
        root = ElementTree.fromstring(content)
        effective = datetime.strptime(root.attrib["Date"], "%d.%m.%Y").date()
        if effective > requested or root.tag != "ValCurs":
            raise ValueError("Invalid rate date")
        rates = {"RUB": Decimal(1)}
        for item in root.findall("Valute"):
            code = item.findtext("CharCode")
            if code not in CURRENCIES:
                continue
            nominal = Decimal(item.findtext("Nominal", "0").replace(" ", ""))
            value = Decimal(item.findtext("Value", "0").replace(" ", "").replace(",", "."))
            if not nominal.is_finite() or not value.is_finite() or nominal <= 0 or value <= 0:
                raise ValueError("Invalid quote")
            rates[code] = value / nominal
        if len(rates) < 2:
            raise ValueError("Empty rate response")
        return effective, rates
    except (ElementTree.ParseError, KeyError, ValueError, InvalidOperation, ZeroDivisionError) as exc:
        raise RateUnavailable("Источник курсов вернул некорректные данные.") from exc


def _remember(cache: OrderedDict, key: date, value: object) -> None:
    cache[key] = value
    cache.move_to_end(key)
    while len(cache) > _CACHE_LIMIT:
        cache.popitem(last=False)


async def _load_daily(requested: date) -> tuple[date, dict[str, Decimal]]:
    row = await db.fetchrow("SELECT effective_date,rates FROM currency_daily_rates WHERE requested_date=$1", requested)
    if row:
        raw = json.loads(row["rates"]) if isinstance(row["rates"], str) else row["rates"]
        result = row["effective_date"], {code: Decimal(value) for code, value in raw.items()}
        _remember(_memory, requested, result)
        return result
    if _failures.get(requested, 0) > time.monotonic():
        raise RateUnavailable("Источник курсов временно недоступен.")
    try:
        async with httpx.AsyncClient(timeout=8.0, follow_redirects=False) as client:
            response = await client.get("https://www.cbr.ru/scripts/XML_daily.asp",
                                        params={"date_req": requested.strftime("%d/%m/%Y")})
            response.raise_for_status()
            result = parse_cbr_xml(response.content, requested)
    except (httpx.HTTPError, RateUnavailable) as exc:
        _remember(_failures, requested, time.monotonic() + _RETRY_SECONDS)
        raise RateUnavailable("Не удалось получить автоматический курс.") from exc
    effective, rates = result
    await db.execute(
        """INSERT INTO currency_daily_rates(requested_date,effective_date,rates) VALUES($1,$2,$3::jsonb)
           ON CONFLICT (requested_date) DO NOTHING""",
        requested, effective, json.dumps({code: str(rate) for code, rate in rates.items()}),
    )
    _remember(_memory, requested, result)
    return result


async def get_daily_rates(requested: date) -> tuple[date, dict[str, Decimal]]:
    if requested in _memory:
        return _memory[requested]
    if requested not in _inflight:
        task = asyncio.create_task(_load_daily(requested))
        _inflight[requested] = task
        # Cleanup belongs to the task, not a waiter which could be cancelled.
        def finished(done: asyncio.Task) -> None:
            if _inflight.get(requested) is done:
                _inflight.pop(requested, None)
            if not done.cancelled():
                done.exception()
        task.add_done_callback(finished)
    return await asyncio.shield(_inflight[requested])


async def get_rate(source: str, target: str, requested: date) -> tuple[Decimal, date]:
    source, target = normalize_currency(source), normalize_currency(target)
    if source == target:
        return Decimal(1), requested
    effective, rates = await get_daily_rates(requested)
    if source not in rates or target not in rates:
        raise RateUnavailable(f"Для {source} → {target} нет курса на выбранную дату.")
    return rates[source] / rates[target], effective
