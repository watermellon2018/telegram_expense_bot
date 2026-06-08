-- Migration: feature_103_recommendation
-- Creates monthly summary tables used by recommendation analytics.

BEGIN;

CREATE TABLE IF NOT EXISTS public.monthly_user_summary (
    id                                 serial PRIMARY KEY,
    user_id                            text NOT NULL REFERENCES public.users(user_id) ON DELETE CASCADE,
    month_key                          text NOT NULL,
    total_expense_full                 numeric(14, 2) NOT NULL DEFAULT 0,
    total_income_full                  numeric(14, 2) NOT NULL DEFAULT 0,
    net_balance_full                   numeric(14, 2) NOT NULL DEFAULT 0,
    tx_count                           integer NOT NULL DEFAULT 0,
    avg_check                          numeric(14, 2) NOT NULL DEFAULT 0,
    median_check                       numeric(14, 2) NOT NULL DEFAULT 0,
    recurring_amount_full              numeric(14, 2) NOT NULL DEFAULT 0,
    recurring_share_full               numeric(7, 4) NOT NULL DEFAULT 0,
    small_expense_amount_full          numeric(14, 2) NOT NULL DEFAULT 0,
    small_expense_share_full           numeric(7, 4) NOT NULL DEFAULT 0,
    total_expense_baseline_adjusted    numeric(14, 2) NOT NULL DEFAULT 0,
    recurring_amount_baseline_adjusted numeric(14, 2) NOT NULL DEFAULT 0,
    created_at                         timestamp NOT NULL DEFAULT now(),
    updated_at                         timestamp NOT NULL DEFAULT now(),
    CONSTRAINT uq_monthly_user_summary_user_month UNIQUE (user_id, month_key)
);

CREATE TABLE IF NOT EXISTS public.monthly_category_summary (
    id                             serial PRIMARY KEY,
    user_id                        text NOT NULL REFERENCES public.users(user_id) ON DELETE CASCADE,
    month_key                      text NOT NULL,
    category_id                    integer NOT NULL REFERENCES public.categories(category_id) ON DELETE CASCADE,
    total_amount_full              numeric(14, 2) NOT NULL DEFAULT 0,
    total_amount_baseline_adjusted numeric(14, 2) NOT NULL DEFAULT 0,
    tx_count                       integer NOT NULL DEFAULT 0,
    share_in_month                 numeric(7, 4) NOT NULL DEFAULT 0,
    created_at                     timestamp NOT NULL DEFAULT now(),
    updated_at                     timestamp NOT NULL DEFAULT now(),
    CONSTRAINT uq_monthly_category_summary_scope UNIQUE (user_id, month_key, category_id)
);

CREATE INDEX IF NOT EXISTS idx_monthly_user_summary_user_month
    ON public.monthly_user_summary(user_id, month_key);

CREATE INDEX IF NOT EXISTS idx_monthly_category_summary_user_month
    ON public.monthly_category_summary(user_id, month_key);

COMMIT;

