"""
Analytics layer for recommendation module.
"""

from abc import ABC, abstractmethod
from calendar import monthrange
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from statistics import median
from typing import Dict, Iterable, List, Mapping, MutableMapping, Optional, Sequence, Tuple

from recommendation.models import AnalyticsSnapshot, RecommendationRequest


class AnalyticsService(ABC):
    """Builds prepared analytics snapshots for downstream layers."""

    @abstractmethod
    async def build_snapshot(self, request: RecommendationRequest) -> AnalyticsSnapshot:
        """Convert raw/prepared inputs into analytics snapshot."""


class PreparedAnalyticsService(AnalyticsService):
    """
    Deterministic analytics builder from prepared inputs.

    The service does not perform SQL calls. All signals are computed from
    already prepared payload (`metrics`, `dimensions`, `events`, `metadata`).
    """

    async def build_snapshot(self, request: RecommendationRequest) -> AnalyticsSnapshot:
        source_metrics: Dict[str, float] = {key: _safe_float(value) for key, value in request.metrics.items()}
        source_dimensions: Dict[str, Mapping[str, float]] = {
            key: {item_key: _safe_float(item_value) for item_key, item_value in value.items()}
            for key, value in request.dimensions.items()
        }
        source_metadata = dict(request.metadata)
        normalized_events = [_normalize_event(item) for item in request.events]
        normalized_events = [item for item in normalized_events if item is not None]

        analytics = _build_current_state(source_metrics, normalized_events)
        analytics.update(
            _build_dynamics(
                source_metrics=source_metrics,
                current_expense=analytics["total_expense"],
                request=request,
            )
        )
        analytics.update(
            _build_structure(
                source_metrics=source_metrics,
                source_dimensions=source_dimensions,
                normalized_events=normalized_events,
                request=request,
                metadata=source_metadata,
            )
        )
        analytics.update(_build_behavioral(normalized_events, analytics))
        positive_metrics, positive_metadata = _build_positive_signals(
            source_metrics=source_metrics,
            structure_metrics=analytics,
            source_dimensions=source_dimensions,
        )
        analytics.update(positive_metrics)
        source_metadata.update(positive_metadata)

        metrics = dict(source_metrics)
        metrics.update(analytics)

        dimensions = dict(source_dimensions)
        dimensions.setdefault(
            "category_share_current",
            _build_category_share_map(
                _aggregate_expense_by_category(normalized_events),
                analytics["total_expense"],
            ),
        )
        dimensions.setdefault(
            "project_vs_personal_spend",
            {
                "project": metrics.get("project_spend", 0.0),
                "personal": metrics.get("personal_spend", 0.0),
            },
        )
        dimensions.setdefault(
            "weekday_spend",
            {
                "weekday": analytics.get("weekday_spend_total", 0.0),
                "weekend": analytics.get("weekend_spend_total", 0.0),
            },
        )

        return AnalyticsSnapshot(
            user_id=request.user_id,
            project_id=request.project_id,
            generated_at=request.requested_at,
            period_start=request.period_start,
            period_end=request.period_end,
            metrics=metrics,
            dimensions=dimensions,
            events=tuple(request.events),
            baseline_metrics=metrics,
            metadata=source_metadata,
        )


def _build_current_state(
    source_metrics: Mapping[str, float],
    events: Sequence[Mapping[str, object]],
) -> Dict[str, float]:
    expense_events = [item for item in events if item["kind"] == "expense"]
    income_events = [item for item in events if item["kind"] == "income"]

    derived_total_expense = sum(item["amount"] for item in expense_events)
    derived_total_income = sum(item["amount"] for item in income_events)
    total_expense = _prefer_metric(
        source_metrics,
        ("total_expense_full", "total_expense"),
        derived_total_expense,
    )
    total_income = _prefer_metric(
        source_metrics,
        ("total_income_full", "total_income"),
        derived_total_income,
    )
    net_balance = _prefer_metric(
        source_metrics,
        ("net_balance_full", "net_balance"),
        total_income - total_expense,
    )
    tx_count = _prefer_metric(source_metrics, ("tx_count",), float(len(expense_events)))
    avg_check = _prefer_metric(
        source_metrics,
        ("avg_check",),
        (total_expense / tx_count) if tx_count > 0 else 0.0,
    )
    median_check = _prefer_metric(
        source_metrics,
        ("median_check",),
        median([item["amount"] for item in expense_events]) if expense_events else 0.0,
    )

    top_category, top_category_amount = _top_category_by_amount(expense_events)
    most_frequent_category, most_frequent_count = _most_frequent_category(expense_events)
    most_expensive_purchase = max((item["amount"] for item in expense_events), default=0.0)
    most_expensive_day, most_expensive_day_amount = _most_expensive_day(expense_events)

    return {
        "total_expense": total_expense,
        "total_income": total_income,
        "net_balance": net_balance,
        "tx_count": tx_count,
        "avg_check": avg_check,
        "median_check": median_check,
        "current_top_category_amount": top_category_amount,
        "current_most_frequent_category_tx_count": float(most_frequent_count),
        "current_most_expensive_purchase": most_expensive_purchase,
        "current_most_expensive_day_amount": most_expensive_day_amount,
        "current_top_category": 0.0 if top_category is None else 1.0,
        "current_most_frequent_category": 0.0 if most_frequent_category is None else 1.0,
        "current_most_expensive_day": 0.0 if most_expensive_day is None else 1.0,
    }


def _build_dynamics(
    source_metrics: Mapping[str, float],
    current_expense: float,
    request: RecommendationRequest,
) -> Dict[str, float]:
    prev_month_total = _prefer_metric(
        source_metrics,
        ("total_expense_prev_month", "prev_month_total_expense", "prev_month_expense"),
        0.0,
    )
    baseline_3m = _prefer_metric(
        source_metrics,
        ("total_expense_3m_baseline", "baseline_3m_total_expense"),
        prev_month_total,
    )
    same_day_prev_month = _prefer_metric(
        source_metrics,
        ("same_day_prev_month_expense",),
        0.0,
    )

    vs_prev_month_abs = current_expense - prev_month_total
    vs_3m_abs = current_expense - baseline_3m
    vs_same_day_abs = current_expense - same_day_prev_month

    vs_prev_month_pct = _safe_percent(vs_prev_month_abs, prev_month_total)
    vs_3m_pct = _safe_percent(vs_3m_abs, baseline_3m)
    vs_same_day_pct = _safe_percent(vs_same_day_abs, same_day_prev_month)

    elapsed_days, total_days = _resolve_period_days(request)
    spend_pace = (current_expense / elapsed_days) if elapsed_days > 0 else 0.0
    spend_forecast = spend_pace * total_days if total_days > 0 else current_expense

    return {
        "delta_vs_prev_month": vs_prev_month_abs,
        "delta_vs_prev_month_pct": vs_prev_month_pct,
        "delta_vs_3m_baseline": vs_3m_abs,
        "delta_vs_3m_baseline_pct": vs_3m_pct,
        "delta_vs_same_day_prev_month": vs_same_day_abs,
        "delta_vs_same_day_prev_month_pct": vs_same_day_pct,
        "spend_pace_per_day": spend_pace,
        "spend_forecast": spend_forecast,
    }


def _build_structure(
    source_metrics: Mapping[str, float],
    source_dimensions: Mapping[str, Mapping[str, float]],
    normalized_events: Sequence[Mapping[str, object]],
    request: RecommendationRequest,
    metadata: Mapping[str, object],
) -> Dict[str, float]:
    total_expense = _prefer_metric(
        source_metrics,
        ("total_expense_full", "total_expense"),
        sum(item["amount"] for item in normalized_events if item["kind"] == "expense"),
    )
    recurring_amount = _prefer_metric(
        source_metrics,
        ("recurring_amount_full", "recurring_amount"),
        sum(
            item["amount"]
            for item in normalized_events
            if item["kind"] == "expense" and item["is_recurring"]
        ),
    )
    recurring_share = _prefer_metric(
        source_metrics,
        ("recurring_share_full", "recurring_share"),
        (recurring_amount / total_expense) if total_expense > 0 else 0.0,
    )

    small_threshold = _safe_float(metadata.get("small_expense_threshold", 200.0))
    small_expense_amount = _prefer_metric(
        source_metrics,
        ("small_expense_amount_full", "small_expense_amount"),
        sum(
            item["amount"]
            for item in normalized_events
            if item["kind"] == "expense" and item["amount"] <= small_threshold
        ),
    )
    small_expense_share = _prefer_metric(
        source_metrics,
        ("small_expense_share_full", "small_expense_share"),
        (small_expense_amount / total_expense) if total_expense > 0 else 0.0,
    )

    category_totals = _aggregate_expense_by_category(normalized_events)
    category_share = _build_category_share_map(category_totals, total_expense)

    project_spend = _prefer_metric(
        source_metrics,
        ("project_spend",),
        total_expense if request.project_id is not None else 0.0,
    )
    personal_spend = _prefer_metric(
        source_metrics,
        ("personal_spend",),
        total_expense if request.project_id is None else 0.0,
    )

    if "category_share_current" not in source_dimensions and category_share:
        source_dimensions = dict(source_dimensions)
        source_dimensions["category_share_current"] = category_share

    return {
        "small_expense_amount": small_expense_amount,
        "small_expense_share": small_expense_share,
        "recurring_amount": recurring_amount,
        "recurring_share": recurring_share,
        "project_spend": project_spend,
        "personal_spend": personal_spend,
    }


def _build_behavioral(
    normalized_events: Sequence[Mapping[str, object]],
    current_metrics: Mapping[str, float],
) -> Dict[str, float]:
    expense_events = [item for item in normalized_events if item["kind"] == "expense"]
    income_events = [item for item in normalized_events if item["kind"] == "income"]

    weekday_total = 0.0
    weekend_total = 0.0
    for item in expense_events:
        if item["event_date"].weekday() < 5:
            weekday_total += item["amount"]
        else:
            weekend_total += item["amount"]

    weekday_vs_weekend_ratio = (weekend_total / weekday_total) if weekday_total > 0 else 0.0

    post_income_spike_count = 0
    post_income_spike_amount = 0.0
    income_dates = sorted([item["event_date"] for item in income_events])
    expense_median = current_metrics.get("median_check", 0.0)
    for expense in expense_events:
        if expense["amount"] <= expense_median:
            continue
        nearest_income = _latest_income_before(expense["event_date"], income_dates)
        if nearest_income is None:
            continue
        if (expense["event_date"] - nearest_income).days <= 3:
            post_income_spike_count += 1
            post_income_spike_amount += expense["amount"]

    repeated_small_count = 0
    repeated_small_amount = 0.0
    small_limit = current_metrics.get("avg_check", 0.0)
    grouped_small = defaultdict(list)
    for item in expense_events:
        if item["amount"] > small_limit:
            continue
        grouped_small[(item["event_date"], item["category_key"])].append(item["amount"])
    for values in grouped_small.values():
        if len(values) < 3:
            continue
        repeated_small_count += len(values)
        repeated_small_amount += sum(values)

    return {
        "weekday_spend_total": weekday_total,
        "weekend_spend_total": weekend_total,
        "weekday_vs_weekend_ratio": weekday_vs_weekend_ratio,
        "post_income_spike_count": float(post_income_spike_count),
        "post_income_spike_amount": post_income_spike_amount,
        "repeated_small_tx_count": float(repeated_small_count),
        "repeated_small_tx_amount": repeated_small_amount,
    }


def _build_positive_signals(
    source_metrics: Mapping[str, float],
    structure_metrics: Mapping[str, float],
    source_dimensions: Mapping[str, Mapping[str, float]],
) -> Tuple[Mapping[str, float], Mapping[str, object]]:
    prev_net_balance = _prefer_metric(source_metrics, ("prev_month_net_balance", "net_balance_prev_month"), 0.0)
    current_net_balance = source_metrics.get("net_balance", structure_metrics.get("net_balance", 0.0))
    balance_delta = current_net_balance - prev_net_balance

    prev_recurring_share = _prefer_metric(
        source_metrics,
        ("prev_month_recurring_share", "recurring_share_prev_month"),
        structure_metrics.get("recurring_share", 0.0),
    )
    current_recurring_share = structure_metrics.get("recurring_share", 0.0)
    recurring_share_delta = current_recurring_share - prev_recurring_share

    current_category_share = source_dimensions.get("category_share_current", {})
    prev_category_share = source_dimensions.get("category_share_prev_month", {})
    reduced_category_key = None
    reduced_category_delta = 0.0
    for category_key, current_value in current_category_share.items():
        prev_value = prev_category_share.get(category_key)
        if prev_value is None:
            continue
        delta = current_value - prev_value
        if delta < reduced_category_delta:
            reduced_category_delta = delta
            reduced_category_key = category_key

    positive_metrics = {
        "positive_improved_balance": 1.0 if balance_delta > 0 else 0.0,
        "positive_balance_delta": balance_delta,
        "positive_reduced_recurring_share": 1.0 if recurring_share_delta < 0 else 0.0,
        "positive_recurring_share_delta": recurring_share_delta,
        "positive_category_reduction": abs(reduced_category_delta) if reduced_category_key else 0.0,
    }
    positive_metadata: Dict[str, object] = {}
    if reduced_category_key is not None:
        positive_metadata["positive_reduced_category_key"] = reduced_category_key
        positive_metadata["positive_reduced_category_delta"] = reduced_category_delta
    return positive_metrics, positive_metadata


def _normalize_event(event: Mapping[str, object]) -> Optional[Mapping[str, object]]:
    amount_raw = event.get("amount")
    if amount_raw is None:
        return None
    amount = _safe_float(amount_raw)
    if amount <= 0:
        return None

    event_date = _resolve_event_date(event)
    if event_date is None:
        return None

    kind_raw = event.get("kind") or event.get("type")
    if kind_raw is None:
        kind = "income" if bool(event.get("is_income")) else "expense"
    else:
        text = str(kind_raw).lower()
        kind = "income" if text in {"income", "in"} else "expense"

    category_key = event.get("category_id")
    if category_key is None:
        category_key = event.get("category") or event.get("category_name")
    if category_key is None:
        category_key = "uncategorized"

    return {
        "amount": amount,
        "kind": kind,
        "event_date": event_date,
        "category_key": str(category_key),
        "is_recurring": bool(event.get("is_recurring", False)),
    }


def _resolve_event_date(event: Mapping[str, object]) -> Optional[date]:
    raw_value = event.get("date") or event.get("occurred_at") or event.get("timestamp")
    if raw_value is None:
        return None
    if isinstance(raw_value, datetime):
        return raw_value.date()
    if isinstance(raw_value, date):
        return raw_value
    try:
        return datetime.fromisoformat(str(raw_value)).date()
    except ValueError:
        return None


def _safe_float(value: object) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _safe_percent(delta: float, base: float) -> float:
    if base == 0:
        return 0.0
    return (delta / base) * 100.0


def _prefer_metric(
    source_metrics: Mapping[str, float],
    keys: Iterable[str],
    fallback: float,
) -> float:
    for key in keys:
        if key in source_metrics:
            return _safe_float(source_metrics.get(key))
    return fallback


def _aggregate_expense_by_category(events: Sequence[Mapping[str, object]]) -> Mapping[str, float]:
    totals: Dict[str, float] = {}
    for item in events:
        if item["kind"] != "expense":
            continue
        category_key = str(item["category_key"])
        totals[category_key] = totals.get(category_key, 0.0) + item["amount"]
    return totals


def _build_category_share_map(
    category_totals: Mapping[str, float],
    total_expense: float,
) -> Mapping[str, float]:
    if total_expense <= 0:
        return {}
    return {key: (value / total_expense) for key, value in category_totals.items()}


def _top_category_by_amount(events: Sequence[Mapping[str, object]]) -> Tuple[Optional[str], float]:
    totals = _aggregate_expense_by_category(events)
    if not totals:
        return None, 0.0
    category_key, amount = max(totals.items(), key=lambda pair: pair[1])
    return category_key, amount


def _most_frequent_category(events: Sequence[Mapping[str, object]]) -> Tuple[Optional[str], int]:
    categories = [str(item["category_key"]) for item in events]
    if not categories:
        return None, 0
    counter = Counter(categories)
    return counter.most_common(1)[0]


def _most_expensive_day(events: Sequence[Mapping[str, object]]) -> Tuple[Optional[date], float]:
    totals: Dict[date, float] = {}
    for item in events:
        totals[item["event_date"]] = totals.get(item["event_date"], 0.0) + item["amount"]
    if not totals:
        return None, 0.0
    event_day, amount = max(totals.items(), key=lambda pair: pair[1])
    return event_day, amount


def _latest_income_before(expense_day: date, income_days: Sequence[date]) -> Optional[date]:
    latest = None
    for income_day in income_days:
        if income_day > expense_day:
            break
        latest = income_day
    return latest


def _resolve_period_days(request: RecommendationRequest) -> Tuple[int, int]:
    if request.period_start and request.period_end and request.period_end >= request.period_start:
        total_days = (request.period_end - request.period_start).days + 1
        current_day = min(request.requested_at.date(), request.period_end)
        if current_day < request.period_start:
            return 0, total_days
        elapsed_days = (current_day - request.period_start).days + 1
        return elapsed_days, total_days

    days_in_month = monthrange(request.requested_at.year, request.requested_at.month)[1]
    elapsed = request.requested_at.day
    return elapsed, days_in_month

