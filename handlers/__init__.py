"""
Инициализация обработчиков команд для Telegram-бота
"""

from handlers.start import register_start_handlers
from handlers.expense import register_expense_handlers
from handlers.stats import register_stats_handlers
from handlers.reminder import register_reminder_handlers
from handlers.export import register_export_handlers
from handlers.project import register_project_handlers

# async def debug_monitor(update, context):
#     print(f"--- DEBUG MONITOR ---")
#     print(f"TEXT: '{update.message.text}'")
#     print(f"BYTES: {update.message.text.encode('utf-8')}")
#     # Это сообщение НЕ прерывает цепочку, оно просто подглядывает
#     return None

def register_all_handlers(application):
    """
    Регистрирует все обработчики команд
    """
    # application.add_handler(MessageHandler(filters.ALL, debug_monitor), group=-1)
    register_project_handlers(application)
    register_start_handlers(application)

    # Важный порядок! В противном случае будет проблема с перехватом сообщений
    # Так как оба метода отслеживают ввод
    register_stats_handlers(application)
    register_expense_handlers(application)
    register_export_handlers(application)

    register_reminder_handlers(application)
