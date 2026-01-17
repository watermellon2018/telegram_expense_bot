"""
Модуль для работы с PostgreSQL через asyncpg.
Предоставляет пул соединений и базовые функции для выполнения запросов.
"""
import os
import asyncpg
import logging
from typing import Optional
import time
from utils.logger import get_logger, log_event, log_error, log_database_operation
from urllib.parse import quote_plus

logger = logging.getLogger(__name__)
db_logger = get_logger("utils.db")

_pool: Optional[asyncpg.Pool] = None

# ── Настройки ────────────────────────────────────────────────
DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_PORT = os.environ.get("DB_PORT", "5432")
DB_NAME = os.environ.get("DB_NAME", "botdb")
DB_USER = os.environ.get("DB_USER", "bot_user")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "")

DSN = f"postgresql://{DB_USER}:{quote_plus(DB_PASSWORD)}@{DB_HOST}:{DB_PORT}/{DB_NAME}"


def extract_table_name(query: str) -> Optional[str]:
    """
    Извлекает название таблицы из SQL запроса
    Возвращает только имя таблицы без скобок и других символов
    """
    try:
        query_upper = query.strip().upper()
        table_name = None
        
        # Для INSERT, UPDATE, DELETE
        if "INSERT INTO" in query_upper:
            parts = query_upper.split("INSERT INTO")[1].split()
            table_name = parts[0] if parts else None
        elif "UPDATE" in query_upper:
            parts = query_upper.split("UPDATE")[1].split()
            table_name = parts[0] if parts else None
        elif "DELETE FROM" in query_upper:
            parts = query_upper.split("DELETE FROM")[1].split()
            table_name = parts[0] if parts else None
        # Для SELECT
        elif "FROM" in query_upper:
            parts = query_upper.split("FROM")[1].split()
            table_name = parts[0] if parts else None
        
        if table_name:
            # Убираем скобки, запятые и другие символы
            # Оставляем только буквы, цифры и подчеркивание
            table_name = table_name.split('(')[0]  # users(user_id) -> users
            table_name = table_name.split(',')[0]  # users, projects -> users
            table_name = table_name.split(';')[0]  # users; -> users
            return table_name.lower()
        
        return None
    except Exception:
        return None


async def init_pool():
    """
    Инициализирует пул соединений с PostgreSQL
    """
    global _pool
    
    import config
    
    start_time = time.time()
    log_event(db_logger, "db_pool_init_start", status="started")
    
    try:
        _pool = await asyncpg.create_pool(
            dsn=DSN,
            min_size=2,              # Можно даже 1 для тестов
            max_size=15,             # 10–20 — оптимально для бота
            max_queries=50_000,
            max_inactive_connection_lifetime=300.0,  # 5 минут
            timeout=30.0,
            command_timeout=60.0,
            # server_settings={'jit': 'off'}  # опционально, если проблемы с производительностью
        )
        
        duration_ms = (time.time() - start_time) * 1000
        log_event(db_logger, "db_pool_init_success", status="success", duration_ms=duration_ms)
        
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        log_error(db_logger, e, "db_pool_init_error", duration_ms=duration_ms)
        raise


async def close_pool():
    """
    Закрывает пул соединений
    """
    global _pool
    
    start_time = time.time()
    log_event(db_logger, "db_pool_close_start", status="started")
    
    if _pool:
        try:
            await _pool.close()
            duration_ms = (time.time() - start_time) * 1000
            log_event(db_logger, "db_pool_close_success", status="success", duration_ms=duration_ms)
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            log_error(db_logger, e, "db_pool_close_error", duration_ms=duration_ms)


async def execute(query: str, *args, request_id: str = None):
    """
    Выполняет SQL-запрос (INSERT, UPDATE, DELETE)
    
    Args:
        query: SQL запрос
        *args: Параметры запроса
        request_id: ID запроса для трейсинга (опционально)
    """
    start_time = time.time()
    
    try:
        result = await _pool.execute(query, *args)
        duration = time.time() - start_time
        
        # Извлекаем тип операции и таблицу
        operation = query.strip().split()[0].upper()
        table = extract_table_name(query)
        
        # Логируем только если операция медленная или это не служебная операция
        import config
        should_log = True
        if operation in ['INSERT', 'UPDATE'] and table in ['users', 'budget']:
            # Служебные операции логируем только если медленные
            slow_threshold = getattr(config, 'SLOW_DB_QUERY_THRESHOLD', 0.01)
            if duration < slow_threshold:
                should_log = False
        
        if should_log:
            log_database_operation(
                db_logger,
                operation,
                table=table,
                duration=duration,
                request_id=request_id
            )
        
        return result
    except Exception as e:
        duration = time.time() - start_time
        log_error(db_logger, e, "db_execute_error", 
                 request_id=request_id,
                 duration_ms=duration * 1000,
                 operation=operation if 'operation' in locals() else 'UNKNOWN',
                 table=table if 'table' in locals() else None)
        raise


async def fetch(query: str, *args, request_id: str = None):
    """
    Выполняет SELECT-запрос и возвращает все строки
    
    Args:
        query: SQL запрос
        *args: Параметры запроса
        request_id: ID запроса для трейсинга (опционально)
    """
    start_time = time.time()
    
    try:
        rows = await _pool.fetch(query, *args)
        duration = time.time() - start_time
        
        # Извлекаем таблицу
        table = extract_table_name(query)
        
        # Логируем SELECT только если медленный
        import config
        slow_threshold = getattr(config, 'SLOW_DB_QUERY_THRESHOLD', 0.05)
        if duration >= slow_threshold:
            log_database_operation(
                db_logger,
                'SELECT',
                table=table,
                duration=duration,
                rows_returned=len(rows) if rows else 0,
                request_id=request_id
            )
        
        return rows
    except Exception as e:
        duration = time.time() - start_time
        log_error(db_logger, e, "db_fetch_error", 
                 request_id=request_id,
                 duration_ms=duration * 1000,
                 table=table if 'table' in locals() else None)
        raise


async def fetchrow(query: str, *args, request_id: str = None):
    """
    Выполняет SELECT-запрос и возвращает одну строку
    
    Args:
        query: SQL запрос
        *args: Параметры запроса
        request_id: ID запроса для трейсинга (опционально)
    """
    return await _pool.fetchrow(query, *args)


async def fetchval(query: str, *args, request_id: str = None):
    """
    Выполняет SELECT-запрос и возвращает одно значение
    
    Args:
        query: SQL запрос
        *args: Параметры запроса
        request_id: ID запроса для трейсинга (опционально)
    """
    return await _pool.fetchval(query, *args)
