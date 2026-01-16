# 📊 Расширенное логирование - Руководство

## Что добавлено

### 1. Поддержка всех уровней логирования
- ✅ **INFO** - обычные операции
- ✅ **WARNING** - предупреждения
- ✅ **ERROR** - ошибки с traceback
- ✅ **DEBUG** - детальная отладка

### 2. JSON формат для production
```bash
export JSON_LOG_FORMAT=true
```

**Пример JSON лога:**
```json
{
  "timestamp": "2026-01-16T19:30:36.526225Z",
  "level": "INFO",
  "service": "handlers.expense",
  "event": "expense_added",
  "request_id": "req_12345",
  "user_id": 400564356,
  "status": "success",
  "duration_ms": 15.5,
  "amount": 100.0,
  "category": "продукты"
}
```

### 3. Request ID для связывания операций
Каждое входящее обновление получает уникальный `request_id = req_{update_id}`:

```
message_received    request_id=req_12345 → 
command_executed    request_id=req_12345 → 
expense_added       request_id=req_12345 → 
database_operation  request_id=req_12345
```

Теперь можно отследить весь путь обработки запроса!

### 4. Duration в миллисекундах
Все операции логируют `duration_ms`:

```
[timestamp] INFO [handlers.expense] expense_added request_id=req_123 user_id=456 status=success duration_ms=15.5
```

### 5. Статус операции
Каждая операция имеет статус:
- **success** - успешно выполнена
- **failed** - ошибка
- **skipped** - пропущена
- **started** - начата
- **received** - получена

## Формат логов

### Читаемый формат (по умолчанию)
```
[timestamp] LEVEL [module] event request_id=... user_id=... status=... duration_ms=... other_fields=...
```

**Пример:**
```
[2026-01-16T19:30:36.526Z] INFO     [handlers.expense] expense_added        request_id=req_123 user_id=456 status=success duration_ms=15.5 amount=100.0 category=продукты
```

### JSON формат (для production)
```json
{"timestamp": "...", "level": "...", "service": "...", "event": "...", "request_id": "...", ...}
```

## Настройка

### В `.env` или переменных окружения:
```bash
# Уровень логирования
LOG_LEVEL=INFO  # или DEBUG, WARNING, ERROR

# JSON формат (для production/мониторинга)
JSON_LOG_FORMAT=true  # или false для читаемого формата

# Файл логов (опционально)
LOG_FILE=/var/log/telegram_bot.log
```

### В `config.py`:
```python
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
JSON_LOG_FORMAT = os.getenv("JSON_LOG_FORMAT", "false").lower() == "true"
LOG_FILE = os.getenv("LOG_FILE", None)
```

## Примеры использования

### В коде:
```python
from utils.logger import get_logger, log_event, log_error
import time

logger = get_logger("my_module")

async def my_function(update, context):
    start_time = time.time()
    request_id = context.user_data.get('request_id')
    user_id = update.effective_user.id
    
    try:
        # Ваш код
        result = await some_operation()
        
        duration_ms = (time.time() - start_time) * 1000
        log_event(
            logger,
            "operation_success",
            request_id=request_id,
            user_id=user_id,
            status="success",
            duration_ms=duration_ms,
            result=result
        )
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        log_error(
            logger,
            e,
            "operation_failed",
            request_id=request_id,
            user_id=user_id,
            duration_ms=duration_ms
        )
```

## Примеры логов

### Успешное добавление расхода:
```
[2026-01-16T19:30:36.100Z] INFO     [telegram.updates] message_received     request_id=req_12345 user_id=456 status=received command=/add
[2026-01-16T19:30:36.105Z] INFO     [handlers.expense] text_message_processing request_id=req_12345 user_id=456
[2026-01-16T19:30:36.120Z] INFO     [utils.excel     ] add_expense_start    request_id=req_12345 user_id=456 amount=100.0 category=продукты
[2026-01-16T19:30:36.135Z] INFO     [utils.db        ] database_operation   request_id=req_12345 action=INSERT table=expenses duration_ms=12.5
[2026-01-16T19:30:36.140Z] INFO     [utils.excel     ] add_expense_success  request_id=req_12345 user_id=456 status=success duration_ms=20.0
[2026-01-16T19:30:36.145Z] INFO     [handlers.expense] expense_added_from_text request_id=req_12345 user_id=456 status=success duration_ms=45.0
```

### Ошибка:
```
[2026-01-16T19:30:36.200Z] ERROR    [handlers.expense] expense_add_failed   request_id=req_12345 user_id=456 status=failed duration_ms=15.5 error=Database connection failed error_type=ConnectionError
```

### Пропущенная операция:
```
[2026-01-16T19:30:36.250Z] INFO     [handlers.expense] text_not_parsed_as_expense request_id=req_12345 user_id=456 status=skipped reason=parse_failed
```

## Анализ логов

### Найти все операции по request_id:
```bash
# Читаемый формат
grep "request_id=req_12345" logs.txt

# JSON формат
jq 'select(.request_id=="req_12345")' logs.json
```

### Найти медленные операции (> 100ms):
```bash
# Читаемый формат
grep "duration_ms" logs.txt | awk '$NF > 100'

# JSON формат
jq 'select(.duration_ms > 100)' logs.json
```

### Найти все ошибки пользователя:
```bash
# Читаемый формат
grep "user_id=456" logs.txt | grep ERROR

# JSON формат
jq 'select(.user_id==456 and .level=="ERROR")' logs.json
```

### Статистика по статусам:
```bash
# JSON формат
jq -r '.status' logs.json | sort | uniq -c
```

## Мониторинг

JSON формат идеально подходит для:
- **ELK Stack** (Elasticsearch, Logstash, Kibana)
- **Grafana Loki**
- **Datadog**
- **CloudWatch**
- **Prometheus** (через log exporters)

Каждая строка - валидный JSON объект, легко парсится и индексируется.

## Производительность

- **request_id** добавляется автоматически в `context.user_data`
- **duration_ms** вычисляется в миллисекундах для точности
- **JSON формат** немного медленнее, но незначительно
- Фильтрация служебных операций БД уменьшает объем логов

## Рекомендации

### Development:
```bash
LOG_LEVEL=DEBUG
JSON_LOG_FORMAT=false
```

### Production:
```bash
LOG_LEVEL=INFO
JSON_LOG_FORMAT=true
LOG_FILE=/var/log/telegram_bot.log
```

### Monitoring:
```bash
LOG_LEVEL=WARNING
JSON_LOG_FORMAT=true
```

## Что логируется

- ✅ Все входящие сообщения и callback queries
- ✅ Все команды с параметрами
- ✅ Все операции с БД
- ✅ Все ошибки с traceback
- ✅ Валидация и причины неудач
- ✅ Производительность операций
- ✅ Статусы операций

## Связывание операций

Благодаря `request_id` можно отследить:

1. **Входящее сообщение** → `message_received`
2. **Парсинг** → `text_message_processing`
3. **Валидация** → `amount_validated`, `category_validated`
4. **Добавление в БД** → `add_expense_start`, `database_operation`
5. **Успех** → `add_expense_success`, `expense_added`

Все с одним `request_id`!

## Итог

Теперь логи:
- Структурированы
- Содержат все уровни (INFO, WARNING, ERROR, DEBUG)
- Поддерживают JSON для мониторинга
- Включают `request_id` для связывания операций
- Показывают `duration_ms` для анализа производительности
- Имеют `status` для понимания результата
- Готовы для production и мониторинга
