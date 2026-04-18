BEGIN;

CREATE TABLE IF NOT EXISTS public.income_categories (
    income_category_id SERIAL PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES public.users(user_id) ON DELETE CASCADE,
    project_id INTEGER REFERENCES public.projects(project_id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    is_system BOOLEAN NOT NULL DEFAULT FALSE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_income_categories_active_unique_normalized
    ON public.income_categories (
        user_id,
        COALESCE(project_id, -1),
        LOWER(REGEXP_REPLACE(BTRIM(name), '\\s+', ' ', 'g'))
    )
    WHERE is_active = TRUE;

CREATE INDEX IF NOT EXISTS idx_income_categories_user_id
    ON public.income_categories (user_id);

CREATE INDEX IF NOT EXISTS idx_income_categories_project_id
    ON public.income_categories (project_id);

CREATE TABLE IF NOT EXISTS public.recurring_incomes (
    id SERIAL PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES public.users(user_id) ON DELETE CASCADE,
    amount NUMERIC NOT NULL CHECK (amount > 0),
    income_category_id INTEGER NOT NULL REFERENCES public.income_categories(income_category_id) ON DELETE RESTRICT,
    comment TEXT NOT NULL DEFAULT '',
    project_id INTEGER REFERENCES public.projects(project_id) ON DELETE SET NULL,
    frequency_type TEXT NOT NULL CHECK (frequency_type IN (
        'daily',
        'every_n_days',
        'weekly',
        'every_n_weeks',
        'monthly',
        'every_n_months'
    )),
    interval_value INTEGER CHECK (interval_value IS NULL OR interval_value >= 1),
    weekday INTEGER CHECK (weekday IS NULL OR weekday BETWEEN 1 AND 7),
    day_of_month INTEGER CHECK (day_of_month IS NULL OR day_of_month BETWEEN 1 AND 31),
    is_last_day_of_month BOOLEAN NOT NULL DEFAULT FALSE,
    start_date DATE NOT NULL,
    next_run_at TIMESTAMP NOT NULL,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'paused')),
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_rec_income_interval_for_every_n CHECK (
        frequency_type NOT IN ('every_n_days', 'every_n_weeks', 'every_n_months')
        OR interval_value IS NOT NULL
    )
);

CREATE INDEX IF NOT EXISTS idx_recurring_incomes_next_run
    ON public.recurring_incomes (next_run_at)
    WHERE status = 'active';

CREATE INDEX IF NOT EXISTS idx_recurring_incomes_user_id
    ON public.recurring_incomes (user_id);

CREATE TABLE IF NOT EXISTS public.incomes (
    id SERIAL PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES public.users(user_id) ON DELETE CASCADE,
    amount NUMERIC NOT NULL CHECK (amount > 0),
    income_category_id INTEGER NOT NULL REFERENCES public.income_categories(income_category_id) ON DELETE RESTRICT,
    project_id INTEGER REFERENCES public.projects(project_id) ON DELETE CASCADE,
    description TEXT,
    month INTEGER NOT NULL CHECK (month BETWEEN 1 AND 12),
    income_date DATE NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    recurring_income_id INTEGER REFERENCES public.recurring_incomes(id) ON DELETE SET NULL,
    created_by_system BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS idx_incomes_project_month
    ON public.incomes (project_id, month)
    WHERE project_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_incomes_user_month
    ON public.incomes (user_id, month)
    WHERE project_id IS NULL;

CREATE INDEX IF NOT EXISTS idx_incomes_income_date
    ON public.incomes (income_date);

CREATE INDEX IF NOT EXISTS idx_incomes_income_category_id
    ON public.incomes (income_category_id);

CREATE INDEX IF NOT EXISTS idx_incomes_recurring_income_day
    ON public.incomes (recurring_income_id, income_date)
    WHERE recurring_income_id IS NOT NULL;

COMMIT;
