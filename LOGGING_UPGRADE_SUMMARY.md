# 🚀 Апгрейд логирования - Сводка

## ✅ Что сделано

### 1. Все уровни логирования
- ✅ INFO - обычные операции
- ✅ WARNING - предупреждения  
- ✅ ERROR - ошибки с traceback
- ✅ DEBUG - детальная отладка

### 2. JSON формат
```bash
export JSON_LOG_FORMAT=true
```

**До:**
```
[timestamp] INFO [module] event user_id=123
```

**После (JSON):**
```json
{"timestamp":"2026-01-16T19:30:36Z","level":"INFO","service":"module","event":"event","request_id":"req_123","user_id":123,"status":"success","duration_ms":15.5}
```

### 3. Request ID для связывания операций
```
message_received    request_id=req_12345 →
command_executed    request_id=req_12345 →
expense_added       request_id=req_12345 →
database_operation  request_id=req_12345
```

Теперь можно отследить весь путь обработки!

### 4. Duration в миллисекундах
```
duration_ms=15.5  # точность до 0.01 мс
```

### 5. Статус операции
- `success` - успешно
- `failed` - ошибка
- `skipped` - пропущено
- `started` - начато
- `received` - получено

## Формат

### Читаемый (по умолчанию):
```
[timestamp] LEVEL [module] event request_id=... user_id=... status=... duration_ms=...
```

### JSON (для production):
```json
{"timestamp":"...","level":"...","service":"...","event":"...","request_id":"...","user_id":...,"status":"...","duration_ms":...}
```

## Конфигурация

### `.env`:
```bash
LOG_LEVEL=INFO              # INFO, DEBUG, WARNING, ERROR
JSON_LOG_FORMAT=true        # true для JSON, false для читаемого
LOG_FILE=/var/log/bot.log  # опционально
```

### `config.py`:
```python
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
JSON_LOG_FORMAT = os.getenv("JSON_LOG_FORMAT", "false").lower() == "true"
LOG_FILE = os.getenv("LOG_FILE", None)
```

## Изменения в коде

### `utils/logger.py`:
- ✅ Добавлен `StructuredFormatter` с поддержкой JSON
- ✅ `log_event()` принимает `request_id`, `status`, `duration_ms`
- ✅ `log_command()` принимает `request_id`
- ✅ `log_error()` принимает `request_id`, `duration_ms`
- ✅ Автоопределение формата из `config.JSON_LOG_FORMAT`

### `utils/logging_middleware.py`:
- ✅ Генерирует `request_id = req_{update_id}`
- ✅ Сохраняет в `context.user_data['request_id']`
- ✅ Все логи middleware включают `request_id` и `status`

### `handlers/expense.py`:
- ✅ Добавлен `request_id` во все логи
- ✅ Добавлен `duration_ms` для операций
- ✅ Добавлен `status` (success/failed/skipped)

### `config.py`:
- ✅ Добавлен `JSON_LOG_FORMAT`

## Примеры

### Успешная операция:
```
[2026-01-16T19:30:36Z] INFO [handlers.expense] expense_added request_id=req_123 user_id=456 status=success duration_ms=15.5 amount=100.0
```

### Ошибка:
```
[2026-01-16T19:30:36Z] ERROR [handlers.expense] expense_add_failed request_id=req_123 user_id=456 status=failed duration_ms=25.3 error=Database error
```

### Пропущено:
```
[2026-01-16T19:30:36Z] INFO [handlers.expense] text_not_parsed request_id=req_123 user_id=456 status=skipped reason=invalid_format
```

## Анализ логов

### Найти все операции по request_id:
```bash
# Читаемый
grep "request_id=req_123" logs.txt

# JSON
jq 'select(.request_id=="req_123")' logs.json
```

### Медленные операции (> 100ms):
```bash
# Читаемый
grep "duration_ms" logs.txt | awk '$NF > 100'

# JSON
jq 'select(.duration_ms > 100)' logs.json
```

### Все ошибки:
```bash
# Читаемый
grep "ERROR" logs.txt

# JSON
jq 'select(.level=="ERROR")' logs.json
```

## Мониторинг

JSON формат готов для:
- ELK Stack
- Grafana Loki
- Datadog
- CloudWatch
- Prometheus

## Рекомендации

**Development:**
```bash
LOG_LEVEL=DEBUG
JSON_LOG_FORMAT=false
```

**Production:**
```bash
LOG_LEVEL=INFO
JSON_LOG_FORMAT=true
```

## Тесты

✅ 33/33 тестов проходят
✅ JSON формат работает
✅ Все уровни логирования работают
✅ request_id связывает операции
✅ duration_ms измеряется корректно
✅ status отображается правильно

## Готово к использованию!

Запускайте бота:
```bash
# Development
python main.py

# Production с JSON
export JSON_LOG_FORMAT=true
python main.py
```

Логи будут структурированными, с request_id для трейсинга и duration_ms для анализа производительности!
