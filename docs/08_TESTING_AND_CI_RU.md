# 8. Тестирование и CI/CD

## 8.1. Локальный запуск тестов

Установка dev-зависимостей:

```bash
pip install -r requirements-dev.txt
```

Запуск:

```bash
pytest
```

С покрытием:

```bash
pytest --cov=handlers --cov=utils --cov-report=html --cov-report=term-missing
```

## 8.2. Pytest конфигурация

`pytest.ini`:

- `testpaths = tests`
- `asyncio_mode = auto`
- default addopts включает:
  - verbose,
  - strict-markers,
  - traceback short,
  - coverage по `handlers` и `utils`.

## 8.3. Структура тестов

В `tests/` присутствуют группы:

- `test_handlers_*` — проверка handler-ов и conversation flows.
- `test_utils_*` — доменные утилиты.
- `test_recommendation_*` — полный набор по recommendation layer:
  - analytics,
  - outliers,
  - rules,
  - ranking,
  - formatter,
  - pipeline,
  - Postgres/in-memory repositories,
  - feedback/settings services,
  - e2e flow.

## 8.4. Что критично покрывать при изменениях

- Проверки прав в project scope (`owner/editor/viewer`).
- Идемпотентность recurring job-ов.
- Формат сообщений (регрессионные тесты текста).
- Recommendation thresholds/ranking/dedup.
- SQL-совместимость новых миграций с существующим кодом.

## 8.5. GitHub Actions

### `tests.yml`

- три версии Python: `3.9`, `3.10`, `3.11`;
- установка `requirements.txt` + `requirements-dev.txt`;
- запуск pytest + coverage XML;
- upload в Codecov.

### `deploy.yml`

- триггер: push в `master` и manual dispatch;
- self-hosted runner;
- build/push Docker image в GHCR;
- деплой `docker compose up -d`;
- health check + verify;
- rollback on failure.

### `rollback.yml`

- manual workflow для отката на предыдущую версию.

### `label-issues-in-dev.yml`

- после merge PR в `dev` помечает связанные issue label-ом `in_dev`.

## 8.6. Рекомендуемый pre-merge checklist

1. Прогнать `pytest` локально.
2. Прогнать покрытие и убедиться, что измененные зоны протестированы.
3. Проверить, что тексты и callback patterns не ломают существующие flow.
4. Для изменений в recommendation проверить соответствующие `test_recommendation_*`.
