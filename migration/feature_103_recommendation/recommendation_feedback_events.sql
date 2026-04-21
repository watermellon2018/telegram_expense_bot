-- Migration: feature_103_recommendation
-- Creates recommendation feedback events table.

BEGIN;

CREATE TABLE IF NOT EXISTS public.recommendation_feedback_events (
    id                serial PRIMARY KEY,
    recommendation_id text NOT NULL,
    user_id           text NOT NULL REFERENCES public.users(user_id) ON DELETE CASCADE,
    action_type       text NOT NULL CHECK (
        action_type IN ('shown', 'dismissed', 'liked', 'disliked', 'opened_details')
    ),
    metadata_json     jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at        timestamp NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_recommendation_feedback_rec_created
    ON public.recommendation_feedback_events(recommendation_id, created_at DESC, id DESC);

CREATE INDEX IF NOT EXISTS idx_recommendation_feedback_user_created
    ON public.recommendation_feedback_events(user_id, created_at DESC, id DESC);

COMMIT;

