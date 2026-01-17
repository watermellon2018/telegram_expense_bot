"""
Middleware для логирования всех входящих обновлений
"""
import uuid
from telegram import Update
from telegram.ext import ContextTypes, TypeHandler
from utils.logger import get_logger, log_event

logger = get_logger("telegram.updates")


async def log_update(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Логирует входящее обновление и сохраняет request_id в context
    
    Генерирует уникальный UUID-based request_id один раз на update.
    Этот ID будет использоваться во всех логах при обработке этого update.
    """
    # Генерируем уникальный request_id для этого update
    request_id = str(uuid.uuid4())
    
    # Сохраняем в context для доступа из всех обработчиков
    context.user_data['request_id'] = request_id
    
    user_id = update.effective_user.id if update.effective_user else None
    
    # Логируем сообщения
    if update.message:
        log_event(
            logger,
            "message_received",
            request_id=request_id,
            status="received",
            user_id=user_id
        )
    
    # Логируем callback queries
    elif update.callback_query:
        log_event(
            logger,
            "callback_received",
            request_id=request_id,
            status="received",
            user_id=user_id
        )
    
    # Логируем другие типы обновлений
    else:
        log_event(
            logger,
            "update_received",
            request_id=request_id,
            status="received",
            user_id=user_id
        )


# Создаем handler для всех обновлений
LoggingHandler = TypeHandler(Update, log_update)
