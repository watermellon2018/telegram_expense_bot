"""
Простейший слой доступа к Postgres для бота.
Использует asyncpg и переменные окружения так же, как utils.migration.
"""

import os
import asyncio
from urllib.parse import quote_plus

import asyncpg


DB_HOST = os.environ.get("DB_HOST", "postgres_server")
DB_PORT = os.environ.get("DB_PORT", "5432")
DB_NAME = os.environ.get("DB_NAME", "botdb")
DB_USER = os.environ.get("DB_USER", "bot_user")
DB_PASSWORD = os.environ.get("DB_PASSWORD")

DATABASE_URL = f"postgresql://{DB_USER}:{quote_plus(DB_PASSWORD)}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

import threading

# Хранилище пулов по ID event loop
_pools = {}
_pools_lock = threading.Lock()

# Thread-local для временных соединений (для loops в потоках)
_temp_loop_mode = threading.local()


def _cleanup_closed_pools():
    """Удаляет закрытые пулы из кэша"""
    with _pools_lock:
        closed_ids = []
        for loop_id, pool in _pools.items():
            try:
                if pool.is_closing():
                    closed_ids.append(loop_id)
            except:
                # Пул уже удалён или недоступен
                closed_ids.append(loop_id)
        for loop_id in closed_ids:
            del _pools[loop_id]


async def get_pool() -> asyncpg.Pool:
    """
    Ленивая инициализация пула соединений для текущего event loop.
    Каждый event loop получает свой пул.
    """
    loop = asyncio.get_event_loop()
    loop_id = id(loop)
    
    with _pools_lock:
        # Проверяем, есть ли уже пул для этого loop
        if loop_id in _pools:
            pool = _pools[loop_id]
            # Проверяем, что пул ещё валиден
            try:
                if pool is not None and not pool.is_closing():
                    return pool
            except:
                # Пул был закрыт или удалён, удаляем из кэша
                pass
            del _pools[loop_id]
        
        # Создаём новый пул
        pool = await asyncpg.create_pool(DATABASE_URL, 
                        min_size=5,
                        max_size=10,
                        timeout=60,
                        command_timeout=30, 
                        max_inactive_connection_lifetime=300.0,  # закрывать старые соединения
        )
        # Сохраняем пул напрямую (без weakref, т.к. Pool не поддерживает weakref)
        _pools[loop_id] = pool
        return pool


def run_async(coro):
    """
    Запускает корутину в event loop.
    Если loop уже запущен, создаёт новый loop в отдельном потоке.
    Иначе использует asyncio.run().
    """
    try:
        # Проверяем, есть ли уже запущенный loop
        loop = asyncio.get_running_loop()
        # Если loop запущен, создаём новый в отдельном потоке
        import queue
        
        result_queue = queue.Queue()
        
        def run_in_thread():
            new_loop = None
            conn = None
            try:
                new_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(new_loop)
                
                # Для временных loops создаём прямое соединение вместо пула
                async def run_with_conn():
                    nonlocal conn
                    conn = await asyncpg.connect(DATABASE_URL)
                    # Сохраняем соединение в thread-local для использования в execute/fetch
                    _temp_loop_mode.conn = conn
                    try:
                        return await coro
                    finally:
                        await conn.close()
                        _temp_loop_mode.conn = None
                
                result = new_loop.run_until_complete(run_with_conn())
                result_queue.put(('ok', result))
            except Exception as e:
                result_queue.put(('error', e))
                if conn:
                    try:
                        new_loop.run_until_complete(conn.close())
                    except:
                        pass
            finally:
                if new_loop:
                    try:
                        new_loop.close()
                    except:
                        pass
        
        thread = threading.Thread(target=run_in_thread, daemon=True)
        thread.start()
        thread.join()
        
        status, value = result_queue.get()
        if status == 'error':
            raise value
        return value
    except RuntimeError:
        # Нет запущенного loop, можно использовать asyncio.run
        return asyncio.run(coro)


async def execute(query: str, *args):
    if hasattr(_temp_loop_mode, 'conn') and _temp_loop_mode.conn:
        return await _temp_loop_mode.conn.execute(query, *args)
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.execute(query, *args)


async def fetch(query: str, *args):
    if hasattr(_temp_loop_mode, 'conn') and _temp_loop_mode.conn:
        return await _temp_loop_mode.conn.fetch(query, *args)
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetch(query, *args)


async def fetchrow(query: str, *args):
    if hasattr(_temp_loop_mode, 'conn') and _temp_loop_mode.conn:
        return await _temp_loop_mode.conn.fetchrow(query, *args)
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchrow(query, *args)


