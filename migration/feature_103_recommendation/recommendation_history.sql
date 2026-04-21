-- Migration: feature_103_recommendation
-- Creates recommendation history table for anti-spam, dedup and novelty checks.

BEGIN;

CREATE TABLE IF NOT EXISTS public.recommendation_history (
    id                  serial PRIMARY KEY,
    user_id             text NOT NULL REFERENCES public.users(user_id) ON DELETE CASCADE,
    recommendation_type text NOT NULL,
    period_key          text NOT NULL,
    entity_type         text,
    entity_id           text,
    payload_json        jsonb NOT NULL DEFAULT '{}'::jsonb,
    score               numeric(10, 4) NOT NULL DEFAULT 0,
    status              text NOT NULL DEFAULT 'generated'
                            CHECK (status IN ('generated', 'shown')),
    generated_at        timestamp NOT NULL DEFAULT now(),
    shown_at            timestamp
);

CREATE INDEX IF NOT EXISTS idx_recommendation_history_user_generated
    ON public.recommendation_history(user_id, generated_at DESC, id DESC);

CREATE INDEX IF NOT EXISTS idx_recommendation_history_user_period
    ON public.recommendation_history(user_id, period_key, generated_at DESC, id DESC);

CREATE INDEX IF NOT EXISTS idx_recommendation_history_user_type_period
    ON public.recommendation_history(user_id, recommendation_type, period_key, generated_at DESC, id DESC);

COMMIT;

