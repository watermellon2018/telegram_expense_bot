-- Миграция: создание таблицы постоянных расходов и расширение таблицы expenses
-- Ветка: feature_93

BEGIN;

-- =========================================================
-- 1. Таблица recurring_rules
-- =========================================================
CREATE TABLE IF NOT EXISTS public.recurring_rules (
    id                   SERIAL PRIMARY KEY,

    -- Владелец правила
    user_id              TEXT NOT NULL
                         REFERENCES public.users(user_id) ON DELETE CASCADE,

    -- Поля расхода
    amount               NUMERIC NOT NULL CHECK (amount > 0),
    category_id          INTEGER NOT NULL
                         REFERENCES public.categories(category_id) ON DELETE RESTRICT,
    comment              TEXT NOT NULL DEFAULT '',
    project_id           INTEGER
                         REFERENCES public.projects(project_id) ON DELETE SET NULL,

    -- Тип периодичности
    -- Допустимые значения строго ограничены CHECK-ом
    frequency_type       TEXT NOT NULL
                         CHECK (frequency_type IN (
                             'daily',
                             'every_n_days',
                             'weekly',
                             'every_n_weeks',
                             'monthly',
                             'every_n_months'
                         )),

    -- Количество единиц для типов every_n_*
    -- NULL для daily/weekly/monthly
    interval_value       INTEGER
                         CHECK (interval_value IS NULL OR interval_value >= 1),

    -- День недели: 1=Пн, 7=Вс (ISO)
    -- Используется для weekly и every_n_weeks
    weekday              INTEGER
                         CHECK (weekday IS NULL OR weekday BETWEEN 1 AND 7),

    -- День месяца: 1–31
    -- Используется для monthly и every_n_months
    -- NULL когда is_last_day_of_month = TRUE
    day_of_month         INTEGER
                         CHECK (day_of_month IS NULL OR day_of_month BETWEEN 1 AND 31),

    -- Признак «последний день месяца»
    -- Если TRUE — day_of_month игнорируется
    is_last_day_of_month BOOLEAN NOT NULL DEFAULT FALSE,

    -- Начало действия правила
    start_date           DATE NOT NULL,

    -- Следующее время срабатывания (наивный UTC, как во всём проекте)
    next_run_at          TIMESTAMP NOT NULL,

    -- Статус: active — работает, paused — приостановлено
    status               TEXT NOT NULL DEFAULT 'active'
                         CHECK (status IN ('active', 'paused')),

    created_at           TIMESTAMP NOT NULL DEFAULT now(),
    updated_at           TIMESTAMP NOT NULL DEFAULT now(),

    -- interval_value обязателен для every_n_* типов
    CONSTRAINT chk_interval_for_every_n CHECK (
        frequency_type NOT IN ('every_n_days', 'every_n_weeks', 'every_n_months')
        OR interval_value IS NOT NULL
    )
);

-- Частичный индекс для воркера: выбираем только активные правила,
-- отфильтровывая paused — это ускоряет запрос в несколько раз
CREATE INDEX IF NOT EXISTS idx_recurring_rules_next_run
    ON public.recurring_rules (next_run_at)
    WHERE status = 'active';

-- Индекс для получения всех правил пользователя (экран /recurring)
CREATE INDEX IF NOT EXISTS idx_recurring_rules_user_id
    ON public.recurring_rules (user_id);

-- =========================================================
-- 2. Расширение таблицы expenses
--    Добавляем три колонки для поддержки recurring-расходов
-- =========================================================

-- Источник создания: 'manual' — пользователь вручную, 'recurring' — воркер
ALTER TABLE public.expenses
    ADD COLUMN IF NOT EXISTS source_type TEXT DEFAULT 'manual';

-- Ссылка на правило, по которому создан расход (NULL для ручных)
ALTER TABLE public.expenses
    ADD COLUMN IF NOT EXISTS recurring_rule_id INTEGER
        REFERENCES public.recurring_rules(id) ON DELETE SET NULL;

-- Признак системного создания (TRUE только для расходов от воркера)
ALTER TABLE public.expenses
    ADD COLUMN IF NOT EXISTS created_by_system BOOLEAN DEFAULT FALSE;

-- Индекс для idempotency-проверки в воркере:
-- «уже создан ли расход по этому правилу сегодня?»
CREATE INDEX IF NOT EXISTS idx_expenses_recurring_rule_id
    ON public.expenses (recurring_rule_id, date)
    WHERE recurring_rule_id IS NOT NULL;

COMMIT;
