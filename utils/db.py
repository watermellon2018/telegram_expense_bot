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

_pool = None
_pool_lock = asyncio.Lock()


async def get_pool() -> asyncpg.Pool:
    """
    Ленивая инициализация пула соединений.
    """
    global _pool
    if _pool is not None:
        return _pool
    async with _pool_lock:
        if _pool is None:
            _pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=5)
    return _pool


def run_async(coro):
    """
    Запускает корутину в новом event loop.
    Используем, потому что код бота синхронный.
    """
    return asyncio.run(coro)


async def execute(query: str, *args):
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.execute(query, *args)


async def fetch(query: str, *args):
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetch(query, *args)


async def fetchrow(query: str, *args):
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchrow(query, *args)


