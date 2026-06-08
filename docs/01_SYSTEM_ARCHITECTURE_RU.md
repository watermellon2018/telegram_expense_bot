# 1. Системная архитектура

## 1.1. Что это за система

Проект — Telegram-бот для учета личных и проектных финансов с модулями:

- расходы и категории расходов;
- доходы и категории доходов;
- бюджеты и уведомления;
- recurring-правила (автодобавление расходов/доходов);
- проектный режим с ролями и приглашениями;
- теоретический cashback;
- детерминированные рекомендации;
- экспорт Excel, PDF-отчеты, графики.

## 1.2. Точка входа и запуск

- `main.py`
  - применяет `app/apscheduler_compat.py` (принудительный UTC для APScheduler);
  - строит приложение через `app/bootstrap.py`;
  - запускает `Application.run_polling(drop_pending_updates=True)`.

- `app/bootstrap.py`
  - собирает `telegram.ext.Application`;
  - подключает lifecycle hooks: `post_init=on_startup`, `post_stop=on_shutdown`;
  - регистрирует все handler-ы через `handlers/registry.py`;
  - подключает middleware логирования update и глобальный error handler.

## 1.3. Жизненный цикл приложения

- `app/lifecycle.py::on_startup`
  - создает директорию данных;
  - инициализирует пул PostgreSQL (`utils.db.init_pool`);
  - поднимает Prometheus endpoint (`METRICS_PORT`, по умолчанию `8000`);
  - запускает APScheduler (UTC) с 3 задачами:
    - `budget_notifications` каждые 4 часа;
    - `recurring_expenses` каждые 5 минут;
    - `recurring_incomes` каждые 5 минут.

- `app/lifecycle.py::on_shutdown`
  - останавливает scheduler;
  - закрывает пул БД.

## 1.4. Слои архитектуры

### Telegram слой (`handlers/`)

Отвечает за:

- прием `Update/Context`;
- валидацию пользовательского ввода;
- запуск бизнес-операций в `utils/*` и `recommendation/*`;
- отправку сообщений/файлов/графиков.

Критично: handler-ы регистрируются в фиксированном порядке, потому что есть общий текстовый fallback (`handlers/expense.py::text_handler`), который может перехватывать сообщения.

### Доменный слой (`utils/`)

Включает:

- операции по расходам, доходам, категориям, проектам, бюджетам;
- recurring-логику;
- cashback-логику и snapshots;
- генерацию графиков и PDF;
- проверку прав доступа.

### Recommendation слой (`recommendation/`)

Отдельный модуль с четкой декомпозицией:

- analytics -> outliers -> rules -> ranking -> formatter -> pipeline;
- отдельные репозитории settings/history/feedback/monthly summaries;
- без SQL внутри правил.

### Инфраструктурный слой

- `utils/db.py` — asyncpg pool и SQL-helpers;
- `utils/logger.py` — структурированные логи (JSON/readable);
- `metrics.py` — Prometheus counters/gauges;
- `app/error_handlers.py` — глобальный перехват ошибок PTB.

## 1.5. Поток данных update -> ответ

1. Telegram присылает update.
2. `LoggingHandler` создает `request_id` и пишет входящее событие.
3. PTB выбирает handler по order+filters.
4. Handler вызывает доменные сервисы/утилиты.
5. SQL выполняется через `utils.db` (пул asyncpg).
6. Формируется текст/картинка/файл.
7. Ответ отправляется пользователю.
8. Ошибки попадают в глобальный `error_handler`, где логируются и считаются метрики ошибок.

## 1.6. Файловая структура (практически важная)

- `app/` — сборка и lifecycle.
- `handlers/` — команды, меню, conversation-сценарии.
- `utils/` — доменные операции и инфраструктура.
- `recommendation/` — recommendation subsystem.
- `migration/` — SQL-миграции по фичам.
- `tests/` — unit/regression/integration-like тесты.
- `docs/` — эта документация.

## 1.7. Ключевые архитектурные решения

- PostgreSQL как основной источник истины (даже если в названиях модулей есть legacy `excel`).
- RBAC по ролям проекта (`owner/editor/viewer`) централизован в `utils/permissions.py`.
- Scheduler-driven automation для recurring и budget notifications.
- Recommendation модуль изолирован от Telegram handler-ов и SQL в правилах.
- Детализация observability: structured logs + Prometheus + централизованный error handler.
