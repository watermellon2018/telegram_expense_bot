"""
Alembic environment для telegram_expense_bot (feature_113).

Особенности проекта:
- Рантайм бота использует asyncpg (async). Для миграций используется СИНХРОННЫЙ
  драйвер psycopg (psycopg3) — это стандартный и простой путь для Alembic.
- ORM/SQLAlchemy-моделей в проекте нет: схема описывается сырым SQL.
  Поэтому target_metadata = None и autogenerate НЕ используется — миграции
  пишутся вручную через op.execute(...).

Безопасность:
- URL подключения собирается из тех же переменных окружения, что и у бота
  (DB_HOST/DB_PORT/DB_NAME/DB_USER/DB_PASSWORD; см. utils/db.py). Секреты не
  хранятся в alembic.ini и не логируются.
- Этот модуль НЕ импортирует приложение: никакого Telegram polling, scheduler,
  Prometheus или фоновых задач при запуске alembic-команд.
"""

import os
from logging.config import fileConfig
from urllib.parse import quote_plus

from sqlalchemy import engine_from_config, pool

from alembic import context

# Конфиг Alembic (alembic.ini)
config = context.config

# Настройка логирования из ini (без вывода секретов)
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# В проекте нет ORM-моделей → autogenerate не применяется.
target_metadata = None


def _build_database_url() -> str:
    """
    Собирает синхронный SQLAlchemy URL из переменных окружения бота.

    Использует те же переменные, что utils/db.py:
      DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD
    Драйвер — psycopg (sync). Пароль экранируется через quote_plus.

    Приоритетно можно переопределить готовым URL через ALEMBIC_DATABASE_URL
    (например, для CI/локального теста против отдельной БД).
    """
    explicit = os.environ.get("ALEMBIC_DATABASE_URL")
    if explicit:
        return explicit

    db_host = os.environ.get("DB_HOST", "localhost")
    db_port = os.environ.get("DB_PORT", "5432")
    db_name = os.environ.get("DB_NAME", "botdb")
    db_user = os.environ.get("DB_USER", "bot_user")
    db_password = os.environ.get("DB_PASSWORD", "")

    return (
        f"postgresql+psycopg://{db_user}:{quote_plus(db_password)}"
        f"@{db_host}:{db_port}/{db_name}"
    )


def run_migrations_offline() -> None:
    """
    Запуск миграций в offline-режиме (генерация SQL без подключения к БД).

    Используется редко (например, `alembic upgrade head --sql`). Не выводит
    пароль: URL берётся из окружения и в логи не пишется.
    """
    url = _build_database_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """
    Запуск миграций в online-режиме (обычный путь: подключаемся и применяем).
    """
    # Подставляем URL программно, чтобы не хранить его в alembic.ini.
    configuration = config.get_section(config.config_ini_section) or {}
    configuration["sqlalchemy.url"] = _build_database_url()

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            # compare_type/compare_server_default не нужны: autogenerate не используется.
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
