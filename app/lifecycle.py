"""Application startup and shutdown lifecycle hooks."""

import datetime
import os
from typing import Optional

import pytz
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from prometheus_client import start_http_server
from telegram.ext import Application

import config
from utils.db import close_pool, init_pool
from utils.logger import get_logger, log_event

logger = get_logger("app.lifecycle")
_scheduler: Optional[AsyncIOScheduler] = None


def _build_scheduler(application: Application) -> AsyncIOScheduler:
    from utils.budget_notifier import check_budget_notifications
    from utils.recurring import process_recurring_expenses
    from utils.recurring_incomes import process_recurring_incomes

    scheduler = AsyncIOScheduler(timezone=pytz.UTC)
    scheduler.add_job(
        check_budget_notifications,
        "interval",
        hours=4,
        args=[application.bot],
        id="budget_notifications",
        replace_existing=True,
        next_run_time=datetime.datetime.now(pytz.UTC),
    )
    scheduler.add_job(
        process_recurring_expenses,
        "interval",
        minutes=5,
        args=[application.bot],
        id="recurring_expenses",
        replace_existing=True,
        next_run_time=datetime.datetime.now(pytz.UTC),
    )
    scheduler.add_job(
        process_recurring_incomes,
        "interval",
        minutes=5,
        args=[application.bot],
        id="recurring_incomes",
        replace_existing=True,
        next_run_time=datetime.datetime.now(pytz.UTC),
    )
    return scheduler


async def on_startup(application: Application) -> None:
    """Initialize external resources and background jobs."""
    global _scheduler
    os.makedirs(config.DATA_DIR, exist_ok=True)
    await init_pool()

    metrics_port = int(os.environ.get("METRICS_PORT", "8000"))
    start_http_server(metrics_port, addr="0.0.0.0")
    log_event(logger, "prometheus_metrics_started", port=metrics_port)

    _scheduler = _build_scheduler(application)
    _scheduler.start()
    log_event(
        logger,
        "scheduler_started",
        jobs=["budget_notifications", "recurring_expenses", "recurring_incomes"],
        budget_interval_hours=4,
        recurring_interval_minutes=5,
    )
    log_event(logger, "bot_started", status="success")


async def on_shutdown(application: Application) -> None:
    """Gracefully stop scheduler and database pool."""
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        log_event(logger, "scheduler_stopped")
    await close_pool()
    log_event(logger, "bot_shutdown", status="success")
