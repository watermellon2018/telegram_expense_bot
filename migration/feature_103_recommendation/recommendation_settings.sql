-- Migration: feature_103_recommendation
-- Creates user recommendation settings table.

BEGIN;

CREATE TABLE IF NOT EXISTS public.user_recommendation_settings (
    id                              serial PRIMARY KEY,
    user_id                         text NOT NULL REFERENCES public.users(user_id) ON DELETE CASCADE,
    recommendations_enabled         boolean NOT NULL DEFAULT TRUE,
    max_recommendations_per_request integer NOT NULL DEFAULT 3 CHECK (max_recommendations_per_request >= 1),
    show_positive_recommendations   boolean NOT NULL DEFAULT TRUE,
    hidden_recommendation_types     text[] NOT NULL DEFAULT ARRAY[]::text[],
    monthly_budget_total            numeric(14, 2),
    created_at                      timestamp NOT NULL DEFAULT now(),
    updated_at                      timestamp NOT NULL DEFAULT now(),
    CONSTRAINT uq_user_recommendation_settings_user_id UNIQUE (user_id),
    CONSTRAINT chk_user_rec_monthly_budget_non_negative
        CHECK (monthly_budget_total IS NULL OR monthly_budget_total >= 0)
);

CREATE INDEX IF NOT EXISTS idx_user_recommendation_settings_user_id
    ON public.user_recommendation_settings(user_id);

COMMIT;

