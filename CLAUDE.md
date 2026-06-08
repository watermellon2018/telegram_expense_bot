# CLAUDE.md

Постоянные правила работы с репозиторием. Только то, что **не выводится из кода напрямую**. Описание текущих задач сюда не добавляется.

Telegram-бот для учёта личных и проектных финансов (расходы/доходы, бюджеты, проекты с ролями, кэшбэк, отчёты). Стек: Python (async), `python-telegram-bot` (polling), PostgreSQL через `asyncpg`, APScheduler, Prometheus. Подробная архитектура — в [docs/ARCHITECTURE_RU.md](docs/ARCHITECTURE_RU.md).

## Слои и их границы

Поток: Telegram update → PTB `Application` → handler из `handlers/*` → логика в `utils/*` → ответ.

- **`handlers/*`** — слой представления. Только оркестрация: валидация ввода, вызов `utils/*`, формирование ответа. **SQL здесь не пишем.**
- **`utils/*`** — инфраструктура **и** доменная логика (фактический сервисный/repository-слой, несмотря на имя папки). `db.py` — доступ к БД; `permissions.py` — RBAC; `parsing.py`/`formatting.py`/`menu.py`/`context.py`/`conversation.py` — декомпозиция helper-ов; `helpers.py` — фасад обратной совместимости.
- **`app/*`** — сборка `Application` и lifecycle (init/close пула БД, Prometheus, scheduler).

Неочевидное:
- `utils/excel.py` — это **сервис расходов поверх Postgres**, а НЕ работа с Excel-файлами (имя историческое).
- Порядок регистрации в `handlers/registry.py` **критичен**: `expense.text_handler` перехватывает любой текст и должен идти последним.
- Тексты кнопок меню — **только** в словарях `config.py` (единый источник).
- Новая команда → модуль в `handlers/` + регистрация в `registry.py`. Новая бизнес-логика → в `utils/*`, handler только вызывает и форматирует.

## Запуск и проверка

Локально мейнтейнер использует conda-окружение `telegram_bot` (Windows); в командах вместо `python` может потребоваться полный путь к его интерпретатору.

```bash
python main.py    # запуск бота (нужен .env и доступная PostgreSQL)
pytest            # тесты (как в CI)
```

Покрытие, отдельные тесты, настройка БД — см. [TESTING.md](TESTING.md) и [SETUP_LOCAL.md](SETUP_LOCAL.md).

Линтер/форматтер в проекте **не настроен** (нет black/ruff/flake8/isort/pre-commit). Не вводи новый инструментарий без согласования.

## БД и миграции

- PostgreSQL, `asyncpg`, **сырой SQL, без ORM**. Запросы из доменного кода — через `utils/db.py`; атомарность — через `async with db.transaction() as conn:`.
- Параметры — **только биндами** (`$1, $2, ...`), без ручной склейки SQL-строк.
- `utils/migration.py` — отдельный одноразовый скрипт переноса исторических данных из Excel в Postgres, не часть рантайма.

### Database migrations

- Версионирование схемы — через **Alembic** (`alembic.ini`, `alembic/`). Рантайм бота работает на `asyncpg`; Alembic использует синхронный драйвер `psycopg`. URL берётся из тех же `DB_*`-переменных, что и бот (`alembic/env.py`) — секреты в конфиге не хранятся.
- **ORM-моделей нет**, поэтому `alembic revision --autogenerate` **не используется**. Миграции пишутся **вручную**: `alembic revision -m "описание"`, затем заполнить `upgrade()` идемпотентным DDL через `op.execute(...)` (`CREATE TABLE IF NOT EXISTS`, `ADD COLUMN IF NOT EXISTS`, `DO $$ ... IF NOT EXISTS $$`).
- Создать миграцию (локально, conda `telegram_bot`): `alembic revision -m "..."`. Применить: `alembic upgrade head`.
- При **Docker-деплое миграции применяются автоматически** одноразовым сервисом `migrations` (тот же образ, `alembic upgrade head`) **до старта бота**; при ошибке миграции бот не обновляется. На сервере вручную миграции не запускают.
- `alembic revision --autogenerate` **никогда не запускать на production**. Откат схемы при неудачном деплое — отдельно и вручную (деплой не делает авто-downgrade).
- Историческая консолидация схемы — в baseline-ревизии (`alembic/versions/0001_baseline.py`). Старые сырые `.sql` в `migration/` оставлены как архив (см. `migration/README.md`), новые изменения схемы — только через Alembic.

## Тесты

- pytest, `asyncio_mode = auto`. БД и внешние вызовы (Telegram, asyncpg) **мокаются** — тесты не ходят в реальные сервисы. Общие фикстуры — в `tests/conftest.py`.
- При изменении логики добавляй/обновляй тесты (особенно расходы, права доступа, форматирование). Перед коммитом `pytest` должен проходить; CI гоняет его на push/PR в `master` и `dev`.

## Логирование

- Только структурно через `utils/logger.py` (`get_logger`, `log_event`, `log_command`, `log_error`, `log_database_operation`) — не `print` и не `logging.info("текст")`.
- Прокидывай контекстные поля: `request_id`, `user_id`, `project_id`, `status`, `duration_ms`.
- Не логируй секреты (токен бота, пароль/DSN БД) и чувствительные данные пользователей.

## Безопасность

- Секреты — только через env/`.env` (в `.gitignore`); деплой-секреты — в GitHub Actions Secrets. Не коммить токены/пароли.
- Весь SQL — параметризованный (см. выше).
- Доступ к проектным операциям проверяй через `utils/permissions.py` (`has_permission`/`require_permission`), а не по неявному предположению, что handler вызывает только владелец.

## Definition of Done

1. Границы слоёв соблюдены (SQL в `utils/*`, команды в `registry.py` с верным порядком).
2. Новые DDL-миграции идемпотентны и лежат в `migration/<feature>/`.
3. Логирование структурное, секреты не утекают.
4. Тесты добавлены/обновлены, `pytest` проходит локально.
5. Тексты UI — из `config.py`.

## Требуют моего явного разрешения

- `git push` (любой), force-push, merge PR, перезапись истории (`reset --hard`, `rebase`).
- Запуск workflow вручную (`deploy.yml`, `rollback.yml`, `workflow_dispatch`) — это реальный деплой/откат на self-hosted сервер.
- Сборка/публикация Docker-образов в GHCR, `docker compose up/pull` на сервере.
- Применение миграций или деструктивного SQL (`DROP`, `TRUNCATE`, `DELETE`/`ALTER ... DROP`) к реальной БД.
- Изменение/ротация секретов, установка новых зависимостей или смена инструментария.
