# 4. Модель данных PostgreSQL

## 4.1. Общая картина

Проект использует PostgreSQL как основной source of truth.
Схема развивалась миграциями по фичам; часть старых SQL-скриптов содержит устаревшие поля (`is_active` у `projects`), но актуальная runtime-логика опирается на `deleted_at`.

## 4.2. Базовые таблицы

### `users`

- `user_id` (PK, text)
- `created_at`
- `active_project_id` (nullable FK-like ссылка на `projects.project_id`)

### `projects`

- `project_id` (PK)
- `user_id` (owner)
- `project_name`
- `created_date`
- `deleted_at` (soft-delete)

Примечание: исторический `is_active` удаляется миграциями feature_82.

### `project_members`

- `(project_id, user_id)` PK
- `role` (`owner|editor|viewer`)
- `joined_at`

### `project_invites`

- `token` PK
- `project_id`
- `inviter_id`
- `role`
- `created_at`
- `expires_at`

## 4.3. Расходы и категории расходов

### `categories`

- `category_id` PK
- `user_id`
- `name`
- `is_system`
- `is_active`
- `project_id` (nullable)
- `created_at`

Индексы/ограничения:

- уникальность активного имени категории в scope `(project_id, lower(name))`;
- индекс по `user_id`.

### `expenses`

- `id` PK
- `user_id`
- `date`
- `time`
- `amount`
- `category_id` (FK -> `categories`)
- `project_id` (nullable)
- `description`
- `month`
- legacy `category` (text, историческое поле)
- recurring-расширения:
  - `source_type` (`manual`/`recurring`)
  - `recurring_rule_id`
  - `created_by_system`

## 4.4. Бюджеты

### `budgets`

- `id` PK
- `user_id`
- `project_id` (nullable)
- `amount`
- `month`, `year`
- `notify_enabled`
- `notify_threshold`
- `last_notified_spending`
- `threshold_notified_at`
- `overspent_notified_at`
- `created_at`, `updated_at`

Особенности:

- два partial unique index:
  - personal: `(user_id, month, year)` where `project_id is null`;
  - project: `(user_id, project_id, month, year)` where `project_id is not null`.

## 4.5. Доходы

### `income_categories`

- `income_category_id` PK
- `user_id`
- `project_id` (nullable)
- `name`
- `is_system`
- `is_active`
- `created_at`

### `incomes`

- `id` PK
- `user_id`
- `amount`
- `income_category_id`
- `project_id` (nullable)
- `description`
- `month`
- `income_date`
- `created_at`
- `recurring_income_id` (nullable)
- `created_by_system`

### `recurring_incomes`

- структура аналогична recurring расходов:
  - `frequency_type`, `interval_value`, `weekday`, `day_of_month`,
  - `is_last_day_of_month`, `start_date`, `next_run_at`, `status`.

## 4.6. Recurring расходы

### `recurring_rules`

- `id` PK
- `user_id`
- `amount`
- `category_id`
- `comment`
- `project_id`
- `frequency_type`
- `interval_value`
- `weekday`
- `day_of_month`
- `is_last_day_of_month`
- `start_date`
- `next_run_at`
- `status` (`active|paused`)
- `created_at`, `updated_at`

Ключевой индекс:

- `idx_recurring_rules_next_run` partial по `next_run_at` где `status='active'`.

## 4.7. Cashback

### `user_cards`

- `id` PK
- `user_id`
- `card_name`
- `is_active`
- `created_at`, `updated_at`

### `cashback_categories`

- `id` PK
- `name`
- `is_global`
- `user_id` (nullable only for global)
- `created_at`

CHECK-ограничение гарантирует корректный scope:

- global: `is_global=true` и `user_id is null`;
- custom: `is_global=false` и `user_id is not null`.

### `user_cashback_rules`

- `id` PK
- `user_id`
- `user_card_id`
- `cashback_category_id`
- `year`, `month`
- `percent`
- `created_at`, `updated_at`

Уникальность: `(user_card_id, cashback_category_id, year, month)`.

### `cashback_monthly_snapshots`

- `id` PK
- `user_id`
- `year`, `month`
- `total_spent`
- `total_potential_cashback`
- `effective_spent`
- `expenses_count`
- `category_breakdown_json` (jsonb)
- `created_at`

Используется для immutable-результатов в закрытых месяцах.

## 4.8. Recommendation tables

### `user_recommendation_settings`

- user-level настройки рекомендаций:
  - enable/disable,
  - max recommendations,
  - positive signals flag,
  - hidden recommendation types,
  - optional monthly budget.

### `recommendation_history`

- история сгенерированных/показанных рекомендаций:
  - `recommendation_type`,
  - `period_key`,
  - `entity_type/entity_id`,
  - `payload_json`,
  - `score`,
  - `status` (`generated|shown`),
  - timestamps.

### `recommendation_feedback_events`

- события обратной связи:
  - `recommendation_id`,
  - `user_id`,
  - `action_type` (`shown|dismissed|liked|disliked|opened_details`),
  - `metadata_json`,
  - `created_at`.

### `monthly_user_summary`, `monthly_category_summary`

- агрегированные monthly summary таблицы для recommendation analytics,
- хранят как full, так и baseline-adjusted показатели.

## 4.9. Важные миграции

- `feature_53_common_project/*` — унификация project model и membership.
- `feature_79_budget/budget_schema.sql` — бюджеты.
- `feature_93_recurring/recurring_rules.sql` — recurring expenses.
- `feature_94_income/income_schema.sql` — income domain + recurring incomes.
- `feature_95_cashback/*` — cashback domain + snapshots.
- `feature_103_recommendation/*` — recommendation persistence.

## 4.10. Практические caveat-ы

- Часть старых миграций еще использует `projects.is_active`; при анализе опирайтесь на текущий код, где используется `deleted_at`.
- В `expenses` сохранено legacy поле `category` (text), но рабочая связь идет через `category_id`.
- Некоторые операции завязаны на `user_id` как `text`; при ручных SQL-скриптах не забывать касты и формат.
