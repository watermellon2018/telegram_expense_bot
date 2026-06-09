-- =====================================================================
-- prod_catch_up_2026_06.sql
-- Разовый скрипт "догнать" production-схему до состояния, которое ожидает
-- код master (feature_94/95/110 + шаблоны проектов), НЕ трогая модель данных.
--
-- Контекст: prod исторически мигрировался вручную .sql-файлами вразнобой.
-- Фактически отсутствуют только аддитивные вещи (проверено по pg_dump схемы):
--   1. expenses.created_at, expenses.deleted_at + индекс idx_expenses_duplicate_lookup
--   2. таблицы feature_110: project_member_settings, expense_duplicate_reports
--   3. таблицы feature_95:  user_cards, cashback_categories,
--                           user_cashback_rules, cashback_monthly_snapshots
--   4. projects.categories_isolated (текущая фича — эквивалент Alembic 0002)
--
-- Существующий уникальный индекс категорий (categories_user_project_name_lower_idx,
-- по user_id) НЕ трогаем — он соответствует персональной модели категорий,
-- по которой реально работает код (WHERE user_id = ...). baseline-овский
-- categories_project_name_idx СОЗНАТЕЛЬНО не создаём.
--
-- Весь DDL идемпотентный (IF NOT EXISTS / DO $$ ... $$), выполняется атомарно.
-- DDL таблиц 95/110/индекса скопирован дословно из alembic 0001_baseline,
-- чтобы схема совпала с тем, что Alembic будет считать применённым.
-- =====================================================================

BEGIN;

-- ---------------------------------------------------------------------
-- 1. expenses: недостающие колонки + индекс дубликатов
-- ---------------------------------------------------------------------
ALTER TABLE public.expenses
    ADD COLUMN IF NOT EXISTS created_at TIMESTAMP NOT NULL DEFAULT now();

ALTER TABLE public.expenses
    ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMP;

CREATE INDEX IF NOT EXISTS idx_expenses_duplicate_lookup
    ON public.expenses (project_id, category_id, date, created_at)
    WHERE project_id IS NOT NULL AND deleted_at IS NULL;

-- На случай если в проде FK назван иначе (expenses_recurring_rule_id_fkey уже
-- существует и эквивалентен) — baseline проверяет по имени fk_expenses_recurring_rule.
-- НЕ создаём дубль: он не нужен, эквивалентный FK уже есть.

-- ---------------------------------------------------------------------
-- 2. feature_110: project_member_settings, expense_duplicate_reports
--    (DDL дословно из 0001_baseline)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.project_member_settings (
    id                      SERIAL PRIMARY KEY,
    project_id              INTEGER NOT NULL REFERENCES public.projects(project_id) ON DELETE CASCADE,
    user_id                 TEXT NOT NULL REFERENCES public.users(user_id) ON DELETE CASCADE,
    expense_notify_mode     TEXT NOT NULL DEFAULT 'all'
                            CHECK (expense_notify_mode IN ('all', 'large_only', 'disabled')),
    large_expense_threshold NUMERIC
                            CHECK (large_expense_threshold IS NULL OR large_expense_threshold > 0),
    updated_at              TIMESTAMP NOT NULL DEFAULT now(),
    CONSTRAINT uq_project_member_settings UNIQUE (project_id, user_id)
);

CREATE TABLE IF NOT EXISTS public.expense_duplicate_reports (
    id                  SERIAL PRIMARY KEY,
    expense_id          INTEGER NOT NULL REFERENCES public.expenses(id) ON DELETE CASCADE,
    reported_by_user_id TEXT NOT NULL REFERENCES public.users(user_id) ON DELETE CASCADE,
    status              TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'kept', 'deleted')),
    created_at          TIMESTAMP NOT NULL DEFAULT now(),
    resolved_at         TIMESTAMP,
    resolved_by_user_id TEXT REFERENCES public.users(user_id) ON DELETE SET NULL,
    CONSTRAINT uq_expense_report_per_user UNIQUE (expense_id, reported_by_user_id)
);

CREATE INDEX IF NOT EXISTS idx_expense_duplicate_reports_expense
    ON public.expense_duplicate_reports (expense_id);

-- ---------------------------------------------------------------------
-- 3. feature_95: user_cards / cashback_categories /
--    user_cashback_rules / cashback_monthly_snapshots
--    (DDL дословно из 0001_baseline, включая сид глобальных категорий)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.user_cards (
    id         SERIAL PRIMARY KEY,
    user_id    TEXT NOT NULL REFERENCES public.users(user_id) ON DELETE CASCADE,
    card_name  VARCHAR(255) NOT NULL,
    is_active  BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_user_cards_active_name_unique
    ON public.user_cards (
        user_id,
        LOWER(REGEXP_REPLACE(BTRIM(card_name), '\s+', ' ', 'g'))
    )
    WHERE is_active = TRUE;

CREATE INDEX IF NOT EXISTS idx_user_cards_user_id
    ON public.user_cards (user_id);

CREATE TABLE IF NOT EXISTS public.cashback_categories (
    id         SERIAL PRIMARY KEY,
    name       VARCHAR(255) NOT NULL,
    is_global  BOOLEAN NOT NULL DEFAULT FALSE,
    user_id    TEXT NULL REFERENCES public.users(user_id) ON DELETE CASCADE,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_cashback_category_scope CHECK (
        (is_global = TRUE AND user_id IS NULL)
        OR
        (is_global = FALSE AND user_id IS NOT NULL)
    )
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_cashback_categories_global_unique
    ON public.cashback_categories (
        LOWER(REGEXP_REPLACE(BTRIM(name), '\s+', ' ', 'g'))
    )
    WHERE is_global = TRUE;

CREATE UNIQUE INDEX IF NOT EXISTS idx_cashback_categories_user_unique
    ON public.cashback_categories (
        user_id,
        LOWER(REGEXP_REPLACE(BTRIM(name), '\s+', ' ', 'g'))
    )
    WHERE is_global = FALSE;

CREATE INDEX IF NOT EXISTS idx_cashback_categories_user_id
    ON public.cashback_categories (user_id);

CREATE TABLE IF NOT EXISTS public.user_cashback_rules (
    id                   SERIAL PRIMARY KEY,
    user_id              TEXT NOT NULL REFERENCES public.users(user_id) ON DELETE CASCADE,
    user_card_id         INTEGER NOT NULL REFERENCES public.user_cards(id) ON DELETE RESTRICT,
    cashback_category_id INTEGER NOT NULL REFERENCES public.cashback_categories(id) ON DELETE RESTRICT,
    year                 INTEGER NOT NULL CHECK (year BETWEEN 2000 AND 2100),
    month                INTEGER NOT NULL CHECK (month BETWEEN 1 AND 12),
    percent              NUMERIC(5, 2) NOT NULL CHECK (percent >= 0 AND percent <= 100),
    created_at           TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at           TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_user_cashback_rule_month UNIQUE (user_card_id, cashback_category_id, year, month)
);

CREATE INDEX IF NOT EXISTS idx_user_cashback_rules_user_month
    ON public.user_cashback_rules (user_id, year, month);

CREATE INDEX IF NOT EXISTS idx_user_cashback_rules_card
    ON public.user_cashback_rules (user_card_id);

-- Сид глобальных категорий кэшбэка (идемпотентно)
INSERT INTO public.cashback_categories(name, is_global, user_id)
VALUES
    ('продукты', TRUE, NULL),
    ('рестораны', TRUE, NULL),
    ('транспорт', TRUE, NULL),
    ('такси', TRUE, NULL),
    ('маркетплейсы', TRUE, NULL),
    ('аптека', TRUE, NULL),
    ('развлечения', TRUE, NULL)
ON CONFLICT DO NOTHING;

CREATE TABLE IF NOT EXISTS public.cashback_monthly_snapshots (
    id                       SERIAL PRIMARY KEY,
    user_id                  TEXT NOT NULL REFERENCES public.users(user_id) ON DELETE CASCADE,
    year                     INTEGER NOT NULL CHECK (year BETWEEN 2000 AND 2100),
    month                    INTEGER NOT NULL CHECK (month BETWEEN 1 AND 12),
    total_spent              NUMERIC(14, 2) NOT NULL DEFAULT 0,
    total_potential_cashback NUMERIC(14, 2) NOT NULL DEFAULT 0,
    effective_spent          NUMERIC(14, 2) NOT NULL DEFAULT 0,
    expenses_count           INTEGER NOT NULL DEFAULT 0,
    category_breakdown_json  JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at               TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_cashback_monthly_snapshot UNIQUE (user_id, year, month)
);

CREATE INDEX IF NOT EXISTS idx_cashback_monthly_snapshots_user_month
    ON public.cashback_monthly_snapshots (user_id, year, month);

-- ---------------------------------------------------------------------
-- 4. projects.categories_isolated (эквивалент Alembic 0002)
-- ---------------------------------------------------------------------
ALTER TABLE public.projects
    ADD COLUMN IF NOT EXISTS categories_isolated BOOLEAN NOT NULL DEFAULT FALSE;

COMMIT;
