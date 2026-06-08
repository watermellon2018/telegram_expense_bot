"""
Ожидание готовности PostgreSQL перед применением миграций (feature_113).

Используется в Docker-сервисе миграций: внешний Postgres может быть ещё не готов
принимать соединения в момент старта контейнера. Скрипт повторяет попытку
подключения, пока БД не ответит, либо пока не истечёт таймаут.

Подключается тем же sync-драйвером (psycopg), что и Alembic, и берёт параметры
из тех же переменных окружения, что рантайм бота (DB_HOST/DB_PORT/DB_NAME/
DB_USER/DB_PASSWORD). Секреты не печатаются.
"""

import os
import sys
import time

import psycopg


def _conn_kwargs() -> dict:
    # Параметры подключения как kwargs — psycopg сам корректно их экранирует,
    # поэтому спецсимволы в пароле (пробел, кавычка, бэкслеш) не ломают DSN.
    return {
        "host": os.environ.get("DB_HOST", "localhost"),
        "port": os.environ.get("DB_PORT", "5432"),
        "dbname": os.environ.get("DB_NAME", "botdb"),
        "user": os.environ.get("DB_USER", "bot_user"),
        "password": os.environ.get("DB_PASSWORD", ""),
    }


def main() -> int:
    timeout = int(os.environ.get("DB_WAIT_TIMEOUT", "60"))
    interval = float(os.environ.get("DB_WAIT_INTERVAL", "2"))
    deadline = time.monotonic() + timeout

    # Безопасный для логов адрес (без пароля)
    where = f"{os.environ.get('DB_HOST', 'localhost')}:{os.environ.get('DB_PORT', '5432')}"

    attempt = 0
    while True:
        attempt += 1
        try:
            with psycopg.connect(connect_timeout=5, **_conn_kwargs()) as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
            print(f"[wait_for_db] PostgreSQL доступен ({where}) после {attempt} попыток.")
            return 0
        except Exception as exc:  # noqa: BLE001 — нам важен сам факт недоступности
            if time.monotonic() >= deadline:
                print(
                    f"[wait_for_db] PostgreSQL ({where}) недоступен за {timeout}s: "
                    f"{exc.__class__.__name__}",
                    file=sys.stderr,
                )
                return 1
            print(f"[wait_for_db] Ожидание PostgreSQL ({where})... попытка {attempt}")
            time.sleep(interval)


if __name__ == "__main__":
    sys.exit(main())
