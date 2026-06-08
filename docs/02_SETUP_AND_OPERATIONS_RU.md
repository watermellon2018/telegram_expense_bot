# 2. Запуск и эксплуатация

## 2.1. Технологический стек

- Python `3.11` в Docker-образе (локально также используются `3.9/3.10/3.11` в CI).
- `python-telegram-bot` `22.5`.
- `asyncpg` для PostgreSQL.
- `apscheduler` `3.6.3`.
- `pandas`, `openpyxl` для Excel-экспорта.
- `matplotlib`, `seaborn` для графиков/PDF.
- `prometheus_client` для `/metrics`.

## 2.2. Обязательные переменные окружения

Минимально:

- `TELEGRAM_BOT_TOKEN` — токен бота.
- `DB_HOST`
- `DB_PORT`
- `DB_NAME`
- `DB_USER`
- `DB_PASSWORD`

Опционально:

- `LOG_LEVEL` (по умолчанию `INFO`)
- `LOG_FILE` (если нужен файл логов)
- `METRICS_PORT` (по умолчанию `8000`)

## 2.3. Локальный запуск

1. Установить зависимости:

```bash
pip install -r requirements.txt
```

2. Подготовить `.env` с параметрами БД и токеном.

3. Убедиться, что БД содержит нужную схему (через SQL-миграции из `migration/`).

4. Запуск:

```bash
python main.py
```

## 2.4. Docker/серверный запуск

- `Dockerfile` собирает образ и запускает `python main.py`.
- `docker-compose.yml`:
  - контейнер `money_bot`;
  - читает `.env`;
  - пробрасывает метрики `8010:8000`;
  - работает в сети `postgres_net` (external).

## 2.5. GitHub Actions

- `tests.yml`: тесты + coverage на push/PR (`master`, `dev`).
- `deploy.yml`: сборка и push образа в GHCR, деплой на `self-hosted`, rollback при ошибке.
- `rollback.yml`: ручной откат.

Подробности по CI/CD — в `08_TESTING_AND_CI_RU.md`.

## 2.6. Быстрая диагностика проблем

### Бот не стартует

- проверить `TELEGRAM_BOT_TOKEN`;
- проверить доступность PostgreSQL;
- проверить корректность `.env`.

### Ошибка подключения к БД

- проверить host/port/user/password;
- убедиться, что schema-миграции применены;
- посмотреть структурированные логи `utils.db`.

### Нет метрик

- проверить `METRICS_PORT`;
- проверить, что в логах есть событие `prometheus_metrics_started`.

### Не срабатывают recurring/budget уведомления

- проверить событие `scheduler_started`;
- проверить, что scheduler job-ы активны;
- проверить статусы/поля в таблицах `recurring_rules`, `recurring_incomes`, `budgets`.

## 2.7. Операционные рекомендации

- Всегда запускать бот после применения миграций, а не до.
- Для production держать отдельную роль БД с ограниченными правами.
- Для крупных рефакторингов сначала проверить order handler-ов в `handlers/registry.py`.
- При изменении логики recurring всегда учитывать идемпотентность вставок за день.
