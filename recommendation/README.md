# Recommendation Module

Отдельный модуль recommendation system с чистыми слоями:

- `analytics.py` - подготовка `AnalyticsSnapshot`
- `types.py` - единый список типов рекомендаций (MVP enum/const)
- `outliers.py` - обработка выбросов / baseline adjustment
- `rules/base.py` - базовый контракт для rules
- `rule_engine.py` - запуск rules по snapshot
- `ranking.py` - ранжирование и фильтрация кандидатов
- `formatter.py` - преобразование в финальный presentation DTO
- `repositories/*` - интерфейсы и реализации репозиториев settings/history/feedback
  (in-memory + PostgreSQL для user settings и recommendation history)
- `settings_service.py` - сервис create/read/update пользовательских настроек
- `feedback_service.py` - сервис записи и чтения feedback events
- `pipeline.py` - оркестратор всех слоев

Ключевой принцип: правила работают только с `AnalyticsSnapshot` и не делают SQL.
