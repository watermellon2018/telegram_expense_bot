# 📊 Структурированное логирование

## Обзор

Проект использует **детальное структурированное логирование** с обязательными полями:
- **timestamp** - время события (ISO 8601, UTC)
- **level** - уровень логирования (INFO, ERROR, WARNING, DEBUG)
- **service** - название сервиса/модуля
- **event** - название события

**Все операции, сообщения и ошибки логируются с полным контекстом!**

## Дополнительные поля

В зависимости от контекста могут добавляться:
- `user_id` - ID пользователя Telegram
- `project_id` - ID проекта
- `command` - название команды
- `action` - выполняемое действие
- `duration` - длительность операции (секунды)
- `status` - статус операции (success, failed, error)
- `error` - текст ошибки
- `error_type` - тип исключения
- `amount` - сумма расхода
- `category` - категория расхода
- `query` - SQL запрос (первые 100 символов)
- `table` - название таблицы БД
- `filename` - имя файла
- `message` - текстовое сообщение

## Использование

### Базовое использование

```python
from utils.logger import get_logger, log_event

# Создаем логгер для модуля
logger = get_logger("handlers.expense")

# Логируем событие
log_event(logger, "expense_added", user_id=123, amount=100.0, category="продукты")
```

### Логирование команд

```python
from utils.logger import log_command

# Логируем выполнение команды
log_command(logger, "add", user_id=123, project_id=1)
```

### Логирование ошибок

```python
from utils.logger import log_error

try:
    # какой-то код
    pass
except Exception as e:
    log_error(logger, e, "operation_failed", user_id=123, action="add_expense")
```

### Логирование операций с БД

```python
from utils.logger import log_database_operation
import time

start_time = time.time()
# выполнение запроса
duration = time.time() - start_time

log_database_operation(
    logger, 
    "SELECT", 
    table="expenses", 
    duration=duration,
    user_id=123
)
```

### Логирование производительности

```python
from utils.logger import log_performance
import time

start_time = time.time()
# операция
duration = time.time() - start_time

log_performance(logger, "export_excel", duration)
```

### Декоратор для измерения времени

```python
from utils.logger import measure_time

@measure_time(logger, "add_expense")
async def add_expense(user_id, amount, category):
    # код функции
    pass
```

## Форматы вывода

### Читаемый формат (по умолчанию, для разработки)

```
[2026-01-16T12:34:56.789Z] INFO     [handlers.expense] expense_added          user_id=123 command=add - Расход добавлен успешно
```

### JSON формат (для production)

Установите переменную окружения:
```bash
export JSON_LOG_FORMAT=true
```

Или в `.env`:
```
JSON_LOG_FORMAT=true
```

Пример вывода:
```json
{
  "timestamp": "2026-01-16T12:34:56.789Z",
  "level": "INFO",
  "service": "handlers.expense",
  "event": "expense_added",
  "user_id": 123,
  "amount": 100.0,
  "category": "продукты",
  "message": "Расход добавлен успешно"
}
```

## Настройки

В `config.py`:

```python
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
JSON_LOG_FORMAT = os.getenv("JSON_LOG_FORMAT", "false").lower() == "true"
LOG_FILE = os.getenv("LOG_FILE", None)  # Путь к файлу (если None - только консоль)
```

## Примеры событий

### События бота
- `bot_started` - бот запущен
- `bot_shutdown` - бот остановлен
- `bot_stopped` - бот остановлен (прерван)
- `system_initialized` - система инициализирована

### События команд
- `command_executed` - команда выполнена
- `export_start` - начало экспорта
- `export_success` - экспорт успешен
- `export_error` - ошибка экспорта
- `expense_added` - расход добавлен

### События БД
- `db_pool_init_start` - начало инициализации пула
- `db_pool_init_success` - пул инициализирован
- `db_pool_close_start` - начало закрытия пула
- `db_pool_close_success` - пул закрыт
- `database_operation` - операция с БД

### События ошибок
- `error_occurred` - произошла ошибка
- `critical_error` - критическая ошибка
- `db_fetch_error` - ошибка выборки из БД
- `db_execute_error` - ошибка выполнения запроса

## Лучшие практики

1. **Используйте осмысленные названия событий**
   - ✅ `expense_added`
   - ❌ `event1`, `log1`

2. **Добавляйте контекст**
   - Всегда логируйте `user_id` для пользовательских операций
   - Добавляйте `project_id` если операция связана с проектом
   - Логируйте `duration` для долгих операций

3. **Логируйте ошибки с полным контекстом**
   ```python
   log_error(logger, e, "operation_failed", 
            user_id=user_id, 
            action="add_expense",
            amount=amount,
            category=category)
   ```

4. **Используйте правильные уровни**
   - `INFO` - нормальные операции
   - `WARNING` - предупреждения (медленные операции > 1 сек)
   - `ERROR` - ошибки
   - `DEBUG` - отладочная информация

5. **Не логируйте чувствительные данные**
   - ❌ Пароли, токены, персональные данные
   - ✅ ID пользователей, суммы, категории

## Интеграция с мониторингом

JSON формат удобен для интеграции с системами мониторинга:
- ELK Stack (Elasticsearch, Logstash, Kibana)
- Grafana Loki
- Datadog
- CloudWatch Logs

Пример парсинга в Logstash:
```ruby
filter {
  json {
    source => "message"
  }
}
```

## Примеры использования в коде

### handlers/expense.py
```python
from utils.logger import get_logger, log_command, log_event

logger = get_logger("handlers.expense")

async def add_command(update, context):
    user_id = update.effective_user.id
    log_command(logger, "add", user_id=user_id)
    # ...
```

### utils/db.py
```python
from utils.logger import get_logger, log_database_operation, log_error

logger = get_logger("utils.db")

async def fetch(query, *args):
    start_time = time.time()
    try:
        result = await conn.fetch(query, *args)
        duration = time.time() - start_time
        log_database_operation(logger, "SELECT", duration=duration)
        return result
    except Exception as e:
        log_error(logger, e, "db_fetch_error")
        raise
```
