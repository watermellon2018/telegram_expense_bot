"""Prometheus metrics for Telegram bot."""

from typing import Optional

from prometheus_client import Counter, Gauge

try:
    from telegram.error import TelegramError
except Exception:  # pragma: no cover
    TelegramError = Exception  # fallback for runtime environments without telegram import


ERRORS_TOTAL = Counter(
    "errors_total",
    "Total number of errors by type and handler",
    labelnames=("type", "handler"),
)

HANDLER_REQUESTS_TOTAL = Counter(
    "handler_requests_total",
    "Total number of handler requests by status",
    labelnames=("handler", "status"),
)

ACTIVE_REQUESTS = Gauge(
    "active_requests",
    "Current number of in-flight handler requests",
    labelnames=("handler",),
)

BOT_COMMAND_TOTAL = Counter(
    "bot_command_total",
    "Total number of bot command invocations",
    labelnames=("command",),
)

FLOW_STARTED_TOTAL = Counter(
    "flow_started_total",
    "Total number of started flows",
    labelnames=("flow",),
)

FLOW_COMPLETED_TOTAL = Counter(
    "flow_completed_total",
    "Total number of completed flows",
    labelnames=("flow",),
)

FLOW_CANCELLED_TOTAL = Counter(
    "flow_cancelled_total",
    "Total number of cancelled flows",
    labelnames=("flow",),
)


def track_handler_start(handler_name: str) -> None:
    """Marks handler request start by incrementing in-flight gauge."""
    ACTIVE_REQUESTS.labels(handler=handler_name).inc()


def track_handler_success(handler_name: str) -> None:
    """Marks handler successful completion and decrements in-flight gauge."""
    HANDLER_REQUESTS_TOTAL.labels(handler=handler_name, status="success").inc()
    ACTIVE_REQUESTS.labels(handler=handler_name).dec()


def track_handler_error(handler_name: str, error_type: str) -> None:
    """Marks handler error completion and decrements in-flight gauge."""
    HANDLER_REQUESTS_TOTAL.labels(handler=handler_name, status="error").inc()
    ERRORS_TOTAL.labels(type=error_type, handler=handler_name).inc()
    ACTIVE_REQUESTS.labels(handler=handler_name).dec()


def track_error_only(handler_name: str, error_type: str) -> None:
    """Records handler error without changing in-flight gauge."""
    ERRORS_TOTAL.labels(type=error_type, handler=handler_name).inc()


def track_flow_started(flow_name: str) -> None:
    FLOW_STARTED_TOTAL.labels(flow=flow_name).inc()


def track_flow_completed(flow_name: str) -> None:
    FLOW_COMPLETED_TOTAL.labels(flow=flow_name).inc()


def track_flow_cancelled(flow_name: str) -> None:
    FLOW_CANCELLED_TOTAL.labels(flow=flow_name).inc()


def track_command(command_name: str) -> None:
    BOT_COMMAND_TOTAL.labels(command=command_name).inc()


def classify_error_type(error: Optional[Exception]) -> str:
    """Maps exception to one of: db, telegram_api, validation, unknown."""
    if error is None:
        return "unknown"

    name = error.__class__.__name__.lower()
    module = (error.__class__.__module__ or "").lower()

    if "asyncpg" in module or "sql" in name or "database" in name:
        return "db"

    if isinstance(error, TelegramError) or "telegram" in module:
        return "telegram_api"

    if isinstance(error, (ValueError, TypeError, KeyError)):
        return "validation"

    return "unknown"
