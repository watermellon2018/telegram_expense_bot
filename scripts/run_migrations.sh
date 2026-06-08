#!/usr/bin/env sh
# Entrypoint одноразового сервиса миграций (feature_113).
#
# 1. Ждёт готовности PostgreSQL (внешний Postgres может быть ещё не поднят).
# 2. Применяет миграции: alembic upgrade head.
#
# Завершается с ненулевым кодом при любой ошибке, чтобы в Docker-деплое
# падение этого шага останавливало запуск бота.
#
# НЕ запускает alembic revision --autogenerate и НЕ выполняет downgrade.

set -eu

echo "[run_migrations] Ожидание готовности базы данных..."
python scripts/wait_for_db.py

echo "[run_migrations] Применение миграций: alembic upgrade head"
alembic upgrade head

echo "[run_migrations] Миграции применены успешно."
