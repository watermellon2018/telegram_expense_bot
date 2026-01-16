# Тесты для Telegram Expense Bot

## Установка зависимостей для тестирования

```bash
pip install -r requirements-dev.txt
```

## Запуск тестов

### Запустить все тесты
```bash
pytest
```

### Запустить с подробным выводом
```bash
pytest -v
```

### Запустить с покрытием кода
```bash
pytest --cov=handlers --cov=utils --cov-report=html
```

### Запустить конкретный файл с тестами
```bash
pytest tests/test_handlers_start.py
```

### Запустить конкретный тест
```bash
pytest tests/test_handlers_start.py::test_start_command
```

## Структура тестов

- `conftest.py` - Общие fixtures для всех тестов
- `test_handlers_*.py` - Тесты для обработчиков команд
- `test_utils_*.py` - Тесты для вспомогательных функций

## Покрытие кода

После запуска тестов с опцией `--cov-report=html` откройте файл `htmlcov/index.html` для просмотра детального отчета о покрытии кода.

## Добавление новых тестов

При добавлении нового функционала:

1. Создайте соответствующий файл `test_*.py` в директории `tests/`
2. Используйте fixtures из `conftest.py` для mock объектов
3. Добавьте тесты для:
   - Успешных сценариев
   - Обработки ошибок
   - Граничных случаев

## CI/CD Integration

Эти тесты могут быть интегрированы в GitHub Actions или другие CI/CD системы для автоматического запуска при каждом коммите.
