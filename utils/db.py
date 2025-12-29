# db.py — финальная рекомендованная версия

import asyncio
import asyncpg
from contextlib import asynccontextmanager
import os
from urllib.parse import quote_plus
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# ── Настройки ────────────────────────────────────────────────
DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_PORT = os.environ.get("DB_PORT", "5432")
DB_NAME = os.environ.get("DB_NAME", "botdb")
DB_USER = os.environ.get("DB_USER", "bot_user")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "")

DSN = f"postgresql://{DB_USER}:{quote_plus(DB_PASSWORD)}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

# Глобальный пул
_pool: Optional[asyncpg.Pool] = None
_pool_lock = asyncio.Lock()  # Защита от одновременной инициализации


async def init_pool():
    """Инициализация пула соединений — вызывать один раз при старте"""
    global _pool
    async with _pool_lock:
        if _pool is not None:
            return

        logger.info("Инициализация пула соединений с PostgreSQL...")
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
        logger.info("Пул соединений успешно создан")


async def close_pool():
    """Закрытие пула — вызывать при остановке бота"""
    global _pool
    async with _pool_lock:
        if _pool is None:
            return
        logger.info("Закрытие пула соединений...")
        await _pool.close()
        _pool = None
        logger.info("Пул соединений закрыт")


@asynccontextmanager
async def get_connection():
    if _pool is None:
        raise RuntimeError("Пул соединений не инициализирован! Вызовите await init_pool() при старте.")
    
    async with _pool.acquire() as conn:
        yield conn


# ── Удобные функции ──────────────────────────────────────────
async def execute(query: str, *args):
    async with get_connection() as conn:
        return await conn.execute(query, *args)


async def fetch(query: str, *args):
    async with get_connection() as conn:
        return await conn.fetch(query, *args)


async def fetchrow(query: str, *args):
    async with get_connection() as conn:
        return await conn.fetchrow(query, *args)


async def fetchval(query: str, *args):
    async with get_connection() as conn:
        return await conn.fetchval(query, *args)