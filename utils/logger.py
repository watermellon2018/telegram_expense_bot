"""
Модуль для структурированного логирования
"""
import logging
import sys
import json
from datetime import datetime
from typing import Optional, Any, Dict


class StructuredFormatter(logging.Formatter):
    """
    Форматтер для структурированного логирования
    Поддерживает как читаемый, так и JSON формат
    """
    def __init__(self, json_format: bool = True):
        super().__init__()
        self.json_format = json_format
    
    def format(self, record: logging.LogRecord) -> str:
        # Базовые поля
        timestamp = datetime.utcnow().isoformat() + 'Z'
        level = record.levelname
        service = record.name
        event = getattr(record, 'event', 'log_message')
        
        # Собираем все дополнительные поля
        log_data: Dict[str, Any] = {
            'timestamp': timestamp,
            'level': level,
            'service': service,
            'event': event,
        }
        
        # Добавляем дополнительные поля из record
        for key, value in record.__dict__.items():
            if key not in ['name', 'msg', 'args', 'created', 'filename', 'funcName',
                          'levelname', 'levelno', 'lineno', 'module', 'msecs',
                          'message', 'pathname', 'process', 'processName',
                          'relativeCreated', 'thread', 'threadName', 'exc_info',
                          'exc_text', 'stack_info', 'event']:
                if value is not None:
                    log_data[key] = value
        
        # Форматируем в JSON или читаемый формат
        if self.json_format:
            return json.dumps(log_data, ensure_ascii=False, default=str)
        else:
            # Читаемый формат
            parts = [
                f"[{timestamp}]",
                f"{level:8}",
                f"[{service:15}]",
                f"{event:20}",
            ]
            
            # Добавляем дополнительные поля
            extra_fields = []
            
            # Приоритетные поля (показываем первыми)
            priority_keys = ['request_id', 'user_id', 'status', 'duration_ms', 'error']
            for key in priority_keys:
                if key in log_data and key not in ['timestamp', 'level', 'service', 'event']:
                    value = log_data[key]
                    extra_fields.append(f"{key}={value}")
            
            # Остальные поля
            for key, value in log_data.items():
                if key not in ['timestamp', 'level', 'service', 'event'] + priority_keys:
                    extra_fields.append(f"{key}={value}")
            
            if extra_fields:
                parts.append(" ".join(extra_fields))
            
            # Добавляем основное сообщение если есть
            if record.getMessage():
                parts.append("-")
            
            return " ".join(parts)


def get_logger(service: str, json_format: Optional[bool] = None) -> logging.Logger:
    """
    Создает или возвращает логгер с структурированным форматированием
    
    Args:
        service: Название сервиса/модуля
        json_format: Использовать JSON формат (если None, берется из config)
    
    Returns:
        Настроенный логгер
    """
    logger = logging.getLogger(service)
    
    # Если логгер уже настроен, возвращаем его
    if logger.handlers:
        return logger
    
    # Определяем формат из конфига если не указан явно
    if json_format is None:
        import config
        json_format = getattr(config, 'JSON_LOG_FORMAT', False)
    
    # Создаем форматтер
    formatter = StructuredFormatter(json_format=json_format)
    
    # Создаем handler для вывода в консоль
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    
    # Настраиваем логгер
    logger.addHandler(handler)
    
    # Устанавливаем уровень логирования
    import config
    log_level = getattr(config, 'LOG_LEVEL', 'INFO')
    logger.setLevel(getattr(logging, log_level, logging.INFO))
    
    # Отключаем распространение на root logger
    logger.propagate = False
    
    return logger


def log_event(
    logger: logging.Logger,
    event: str,
    level: int = logging.INFO,
    request_id: Optional[str] = None,
    status: Optional[str] = None,
    duration_ms: Optional[float] = None,
    **kwargs
) -> None:
    """
    Логирует событие с дополнительными полями
    
    Args:
        logger: Logger instance
        event: Название события
        level: Уровень логирования
        request_id: ID запроса для связывания операций
        status: Статус операции (success, failed, skipped)
        duration_ms: Длительность операции в миллисекундах
        **kwargs: Дополнительные поля для лога
    """
    extra = {'event': event}
    
    if request_id is not None:
        extra['request_id'] = request_id
    if status is not None:
        extra['status'] = status
    if duration_ms is not None:
        extra['duration_ms'] = round(duration_ms, 2)
    
    extra.update(kwargs)
    logger.log(level, '', extra=extra)


def log_command(
    logger: logging.Logger,
    command: str,
    user_id: Optional[int] = None,
    request_id: Optional[str] = None,
    **kwargs
) -> None:
    """
    Логирует выполнение команды
    
    Args:
        logger: Logger instance
        command: Название команды
        user_id: ID пользователя
        request_id: ID запроса
        **kwargs: Дополнительные поля
    """
    extra = {
        'event': 'command_executed',
        'command': command,
        'status': 'started',
    }
    if user_id is not None:
        extra['user_id'] = user_id
    if request_id is not None:
        extra['request_id'] = request_id
    extra.update(kwargs)
    logger.info('', extra=extra)


def log_error(
    logger: logging.Logger,
    error: Exception,
    event: str,
    request_id: Optional[str] = None,
    duration_ms: Optional[float] = None,
    **kwargs
) -> None:
    """
    Логирует ошибку
    
    Args:
        logger: Logger instance
        error: Исключение
        event: Название события
        request_id: ID запроса
        duration_ms: Длительность операции до ошибки
        **kwargs: Дополнительные поля
    """
    extra = {
        'event': event,
        'error': str(error),
        'error_type': type(error).__name__,
        'status': 'failed',
    }
    
    if request_id is not None:
        extra['request_id'] = request_id
    if duration_ms is not None:
        extra['duration_ms'] = round(duration_ms, 2)
    
    extra.update(kwargs)
    logger.error('', extra=extra, exc_info=True)


def log_database_operation(
    logger: logging.Logger,
    operation: str,
    table: Optional[str] = None,
    duration: Optional[float] = None,
    request_id: Optional[str] = None,
    **kwargs
) -> None:
    """
    Логирует операцию с базой данных
    
    Args:
        logger: Logger instance
        operation: Тип операции (SELECT, INSERT, UPDATE, DELETE)
        table: Название таблицы
        duration: Длительность операции в секундах
        request_id: ID запроса
        **kwargs: Дополнительные поля (query, rows_returned и т.д.)
    """
    duration_ms = duration * 1000 if duration is not None else None
    
    extra = {
        'event': 'database_operation',
        'action': operation,
        'status': 'success',
    }
    
    if table is not None:
        extra['table'] = table
    if duration_ms is not None:
        extra['duration_ms'] = round(duration_ms, 2)
    if request_id is not None:
        extra['request_id'] = request_id
    
    extra.update(kwargs)
    logger.info('', extra=extra)


def log_performance(
    logger: logging.Logger,
    operation: str,
    duration: float,
    request_id: Optional[str] = None,
    status: str = 'success',
    **kwargs
) -> None:
    """
    Логирует производительность операции
    
    Args:
        logger: Logger instance
        operation: Название операции
        duration: Длительность в секундах
        request_id: ID запроса
        status: Статус операции
        **kwargs: Дополнительные поля
    """
    duration_ms = duration * 1000
    
    log_event(
        logger,
        f"{operation}_performance",
        request_id=request_id,
        status=status,
        duration_ms=duration_ms,
        **kwargs
    )


def measure_time(func):
    """
    Декоратор для измерения времени выполнения функции
    """
    import functools
    import time
    
    @functools.wraps(func)
    async def async_wrapper(*args, **kwargs):
        start_time = time.time()
        try:
            result = await func(*args, **kwargs)
            duration = time.time() - start_time
            return result
        except Exception as e:
            duration = time.time() - start_time
            raise
    
    @functools.wraps(func)
    def sync_wrapper(*args, **kwargs):
        start_time = time.time()
        try:
            result = func(*args, **kwargs)
            duration = time.time() - start_time
            return result
        except Exception as e:
            duration = time.time() - start_time
            raise
    
    import asyncio
    if asyncio.iscoroutinefunction(func):
        return async_wrapper
    else:
        return sync_wrapper
