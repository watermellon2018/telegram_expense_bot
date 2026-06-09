BEGIN;

CREATE TABLE IF NOT EXISTS public.cashback_monthly_snapshots (
    id SERIAL PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES public.users(user_id) ON DELETE CASCADE,
    year INTEGER NOT NULL CHECK (year BETWEEN 2000 AND 2100),
    month INTEGER NOT NULL CHECK (month BETWEEN 1 AND 12),
    total_spent NUMERIC(14, 2) NOT NULL DEFAULT 0,
    total_potential_cashback NUMERIC(14, 2) NOT NULL DEFAULT 0,
    effective_spent NUMERIC(14, 2) NOT NULL DEFAULT 0,
    expenses_count INTEGER NOT NULL DEFAULT 0,
    category_breakdown_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_cashback_monthly_snapshot UNIQUE (user_id, year, month)
);

CREATE INDEX IF NOT EXISTS idx_cashback_monthly_snapshots_user_month
    ON public.cashback_monthly_snapshots(user_id, year, month);

COMMIT;
