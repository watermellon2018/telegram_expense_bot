# 6. Recommendation Module

## 6.1. Роль модуля

`recommendation/` — изолированная подсистема персональных рекомендаций по тратам.

Цели:

- детерминированность;
- объяснимость;
- числовая обоснованность;
- ограниченный top-N output.

## 6.2. Архитектурный контракт

Строгая цепочка:

1. `analytics.py` -> строит `AnalyticsSnapshot`.
2. `outliers.py` -> корректирует baseline с учетом выбросов.
3. `rules/*` + `rule_engine.py` -> генерируют `CandidateRecommendation`.
4. `ranking.py` -> rescoring/dedup/top-N.
5. `formatter.py` -> user-facing `FinalRecommendation`.
6. `pipeline.py` -> orchestration + persistence history/feedback.

Критичное правило:

- SQL не должен попадать в правила.

## 6.3. Типы и модели

### Типы (`types.py`)

- `RecommendationType` (MVP enum):
  - forecast overspend,
  - total/category growth,
  - recurring share/review,
  - small expenses accumulation,
  - cashback opportunity,
  - weekday pattern,
  - positive category reduction.

- `RecommendationHistoryStatus` (`generated|shown`).
- `RecommendationFeedbackActionType` (`shown|dismissed|liked|disliked|opened_details`).

### DTO/модели (`models.py`)

- `RecommendationRequest` — вход в pipeline.
- `AnalyticsSnapshot` — единая аналитическая проекция.
- `CandidateRecommendation` — результат rule layer.
- `FinalRecommendation` — формат для показа пользователю.
- `RecommendationHistoryEntry`, `RecommendationFeedback` — persistable сущности.
- `UserRecommendationSettings`, `RecommendationSettings` — пользовательские и runtime настройки.

## 6.4. Analytics layer (`analytics.py`)

`PreparedAnalyticsService` работает только с подготовленными данными из request:

- `metrics` (числа),
- `dimensions` (распределения),
- `events` (транзакционные события),
- `metadata`.

Собирает:

- current state (total/net/avg/median/top patterns);
- dynamics (vs prev month, vs 3m baseline, forecast, spend pace);
- structure (category shares, recurring share, small expenses share);
- behavioral сигналы (weekday/weekend, spikes после дохода, repeat small tx);
- positive signals (улучшения метрик).

## 6.5. Outlier layer (`outliers.py`)

### OutlierDetectionService

Сигналы:

- ratio to user median;
- ratio to category median;
- rarity in history;
- non-recurring behavior;
- tail detection (q95).

Результат:

- `is_large_one_time_purchase`,
- `outlier_score`,
- `outlier_flag_source`.

### BaselineMetricsBuilder

Строит full + baseline-adjusted метрики:

- `total_expense_full` vs `total_expense_baseline_adjusted`;
- `recurring_amount_full` vs `recurring_amount_baseline_adjusted`;
- median/trimmed mean;
- outlier count.

## 6.6. Rules (`rules/mvp.py`)

### Базовые пороги и защита

- минимум истории: `_MIN_HISTORY_TX_COUNT = 5`.
- при сильном distortion из-за outliers (`>= 0.35`) часть rules не срабатывает.

### Набор MVP-правил

- `ForecastOverspendRule`
- `TotalGrowthVsPrevMonthRule`
- `TotalGrowthVs3MBaselineRule`
- `CategoryGrowthVsPrevMonthRule`
- `CategoryGrowthVs3MBaselineRule`
- `HighRecurringShareRule`
- `RecurringReviewRule`
- `SmallExpensesAccumulationRule`
- `WeekdaySpendingPatternRule`
- `CashbackOpportunityRule`
- `PositiveCategoryReductionRule`

Каждое правило возвращает:

- title/rationale,
- score,
- priority,
- actions,
- payload с числовыми полями и `entity_type/entity_id`.

## 6.7. Ranking (`ranking.py`)

`ScoreRankingService` делает:

- базовый приоритет по типу рекомендации;
- severity/impact/confidence scoring;
- novelty penalty по recent history;
- дедупликацию:
  - по similarity groups;
  - по category entity;
- top-N с учетом `settings.max_recommendations`.

## 6.8. Formatter (`formatter.py`)

`DefaultRecommendationFormatter`:

- генерирует понятный текст с конкретными цифрами;
- добавляет примечание при outlier distortion для чувствительных типов;
- учитывает action-подсказки.

## 6.9. Pipeline (`pipeline.py`)

`RecommendationPipeline.generate()`:

1. грузит user settings;
2. строит snapshot;
3. применяет outlier adjustments;
4. применяет settings к snapshot (например monthly_budget_total);
5. запускает rules;
6. берет recent history;
7. ранжирует и форматирует;
8. пишет history (`generated -> shown`).

## 6.10. Репозитории и сервисы

### PostgreSQL репозитории

- `PostgresSettingsRepository`
- `PostgresHistoryRepository`
- `PostgresFeedbackRepository`
- `PostgresMonthlySummaryRepository`

Таблицы: `user_recommendation_settings`, `recommendation_history`, `recommendation_feedback_events`, monthly summaries.

### In-memory репозитории

Используются для тестов/локальных сценариев через `build_default_recommendation_pipeline`.

### Сервисы

- `RecommendationSettingsService`
- `RecommendationFeedbackService`

## 6.11. Интеграция в Telegram handler

`handlers/recommendations.py`:

- собирает request из `excel.get_month_expenses`, `incomes.get_month_incomes`, годовых DataFrame, event-агрегаций;
- детектирует recurring-пары эвристикой по `(category, amount)` повторенным >=3 раз;
- формирует период и метрики для pipeline;
- отправляет рекомендации и id пользователю;
- пишет feedback events `shown`;
- обрабатывает `/rec_like`, `/rec_dislike`, `/rec_dismiss`.

## 6.12. Правила разработки по AGENTS

Для recommendation/analytics задач в этом репозитории действует правило:

- использовать workflow из `recommendation-module` skill;
- соблюдать последовательность стадий;
- не переносить recommendation-бизнес-логику в Telegram handler-ы;
- сохранять модульность `analytics -> rules -> ranking -> formatting -> handlers`.
