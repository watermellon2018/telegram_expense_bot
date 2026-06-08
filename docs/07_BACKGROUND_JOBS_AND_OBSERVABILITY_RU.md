# 7. Фоновые задачи и наблюдаемость

## 7.1. APScheduler задачи

Scheduler поднимается в `app/lifecycle.py` (timezone UTC).

Активные job-ы:

- `budget_notifications`  
  интервал 4 часа, функция `utils.budget_notifier.check_budget_notifications`.

- `recurring_expenses`  
  интервал 5 минут, функция `utils.recurring.process_recurring_expenses`.

- `recurring_incomes`  
  интервал 5 минут, функция `utils.recurring_incomes.process_recurring_incomes`.

## 7.2. Поведение recurring job-ов

### Расходы

- выбирает активные правила с `next_run_at <= now`;
- проверяет идемпотентность: не создан ли расход за текущую дату;
- создает системную запись (`source_type='recurring'`, `created_by_system=true`);
- обновляет `next_run_at`.

### Доходы

Аналогичный подход для `recurring_incomes` и таблицы `incomes`.

## 7.3. Поведение budget notifier

- работает только по бюджетам с `notify_enabled=true` за текущий месяц;
- если расходов нет, уведомление не отправляется;
- отправляет:
  - threshold notification;
  - overspent notification;
- событие каждого типа отправляется один раз в месяц;
- в project scope уведомляет всех участников.

## 7.4. Logging архитектура

### `utils/logger.py`

- structured formatter (JSON или readable);
- утилиты:
  - `log_event`,
  - `log_error`,
  - `log_database_operation`,
  - `log_command`.

### `utils/logging_middleware.py`

- логирует каждый входящий update;
- генерирует `request_id` (UUID);
- кладет `request_id` в `context.user_data` для сквозной трассировки.

## 7.5. Глобальная обработка ошибок

`app/error_handlers.py`:

- перехватывает необработанные исключения PTB;
- логирует `user_id`, `update_id`, stack trace;
- увеличивает счетчик ошибок в Prometheus через `track_error_only`.

## 7.6. Prometheus-метрики (`metrics.py`)

Основные метрики:

- `errors_total{type,handler}`
- `handler_requests_total{handler,status}`
- `active_requests{handler}`
- `bot_command_total{command}`
- `flow_started_total{flow}`
- `flow_completed_total{flow}`
- `flow_cancelled_total{flow}`

Классификация ошибок:

- `db`
- `telegram_api`
- `validation`
- `unknown`

## 7.7. Endpoint метрик

- HTTP endpoint поднимается на `0.0.0.0:<METRICS_PORT>`
- default: `8000`
- в `docker-compose.yml` проброшен как `8010:8000`

## 7.8. Практические рекомендации по диагностике

- При инциденте сначала фильтровать по `request_id`.
- Для DB проблем смотреть пары:
  - `db_*` события в логах,
  - `errors_total{type="db"}`.
- Для деградации handler-ов смотреть:
  - `active_requests`,
  - `handler_requests_total{status="error"}`.
