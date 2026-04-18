import logging
import os
import datetime
import pytz
import apscheduler.util

# 1. СТРОГИЙ ПАТЧ ТАЙМЗОНЫ (должен быть в самом верху)
def patched_astimezone(obj):
    if obj is None: return pytz.UTC
    if hasattr(obj, 'localize'): return obj
    return pytz.UTC

apscheduler.util.astimezone = patched_astimezone
apscheduler.util.get_localzone = lambda: pytz.UTC

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram.ext import Application, ContextTypes
import config
from handlers import register_all_handlers
from utils.db import init_pool, close_pool

# Настройка структурированного логирования
from utils.logger import get_logger

logger = get_logger("main")

# Глобальный экземпляр планировщика
_scheduler: AsyncIOScheduler = None

# Функция, которая выполнится ПОСЛЕ инициализации бота
async def on_startup(application: Application):
    """Вызывается после инициализации Application"""
    global _scheduler
    from utils.logger import log_event
    os.makedirs(config.DATA_DIR, exist_ok=True)
    await init_pool()

    # Запускаем планировщик уведомлений о бюджете и постоянных расходов
    from utils.budget_notifier import check_budget_notifications
    from utils.recurring import process_recurring_expenses
    from utils.recurring_incomes import process_recurring_incomes
    _scheduler = AsyncIOScheduler(timezone=pytz.UTC)
    _scheduler.add_job(
        check_budget_notifications,
        'interval',
        hours=4,
        args=[application.bot],
        id='budget_notifications',
        replace_existing=True,
        next_run_time=datetime.datetime.now(pytz.UTC),  # Запуск сразу при старте
    )
    # Воркер постоянных расходов: проверяет каждые 5 минут
    _scheduler.add_job(
        process_recurring_expenses,
        'interval',
        minutes=5,
        args=[application.bot],
        id='recurring_expenses',
        replace_existing=True,
        next_run_time=datetime.datetime.now(pytz.UTC),  # Запуск сразу при старте
    )
    # Воркер постоянных доходов: проверяет каждые 5 минут
    _scheduler.add_job(
        process_recurring_incomes,
        'interval',
        minutes=5,
        args=[application.bot],
        id='recurring_incomes',
        replace_existing=True,
        next_run_time=datetime.datetime.now(pytz.UTC),
    )
    _scheduler.start()
    log_event(logger, "scheduler_started",
              jobs=["budget_notifications", "recurring_expenses", "recurring_incomes"],
              budget_interval_hours=4,
              recurring_interval_minutes=5)

    log_event(logger, "bot_started", status="success")

# Функция, которая выполнится ПРИ ОСТАНОВКЕ бота
async def on_shutdown(application: Application):
    """Вызывается при остановке Application"""
    global _scheduler
    from utils.logger import log_event
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        log_event(logger, "scheduler_stopped")
    await close_pool()
    log_event(logger, "bot_shutdown", status="success")

def main():
    """Главная точка входа (НЕ асинхронная)"""
    
    from utils.logger import log_event
    
    # Создаем директорию для данных
    os.makedirs(config.DATA_DIR, exist_ok=True)

    # Собираем приложение
    application = (
        Application.builder()
        .token(config.TOKEN)
        .post_init(on_startup)  # Инициализация после создания приложения
        .post_stop(on_shutdown) # Закрытие при остановке
        .build()
    )

    # Регистрация обработчиков
    register_all_handlers(application)
    
    # Добавляем middleware для логирования всех входящих обновлений
    from utils.logging_middleware import LoggingHandler
    
    application.add_handler(LoggingHandler, group=-1)  # Самый низкий приоритет
    
    # Обработчик ошибок
    async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        from utils.logger import log_error, get_logger
        from telegram import Update
        error_logger = get_logger("telegram.errors")
        
        user_id = None
        update_id = None
        if isinstance(update, Update):
            update_id = update.update_id
            if update.effective_user:
                user_id = update.effective_user.id
        
        log_error(
            error_logger,
            context.error,
            "telegram_error",
            user_id=user_id,
            update_id=update_id
        )
    
    application.add_error_handler(error_handler)

    log_event(logger, "system_initialized", status="ready")

    # run_polling САМ создаст и закроет event loop корректно
    application.run_polling(drop_pending_updates=True)


if __name__ == '__main__':
    from utils.logger import log_error
    try:
        main()
    except KeyboardInterrupt:
        from utils.logger import log_event
        log_event(logger, "bot_stopped", status="interrupted", reason="user_action")
    except Exception as e:
        log_error(logger, e, "critical_error", status="failed")
