-- Migration: feature_79_budget
-- Creates the budgets table for monthly budget tracking with notifications.

CREATE TABLE IF NOT EXISTS public.budgets (
    id                      serial PRIMARY KEY,
    user_id                 text NOT NULL REFERENCES public.users(user_id) ON DELETE CASCADE,
    project_id              integer REFERENCES public.projects(project_id) ON DELETE CASCADE,
    amount                  numeric NOT NULL DEFAULT 0,
    month                   integer NOT NULL CHECK (month BETWEEN 1 AND 12),
    year                    integer NOT NULL,
    notify_enabled          boolean NOT NULL DEFAULT false,
    notify_threshold        numeric,            -- Spending level that triggers the alert
    last_notified_spending  numeric,            -- Spending level at last sent notification
    threshold_notified_at   timestamp,          -- When the threshold alert was last sent
    overspent_notified_at   timestamp,          -- When the overspent alert was last sent
    created_at              timestamp DEFAULT now(),
    updated_at              timestamp DEFAULT now()
);

-- One personal budget per (user, month, year) when project_id IS NULL
CREATE UNIQUE INDEX IF NOT EXISTS budgets_personal_uniq
    ON public.budgets(user_id, month, year)
    WHERE project_id IS NULL;

-- One project budget per (user, project, month, year) when project_id IS NOT NULL
CREATE UNIQUE INDEX IF NOT EXISTS budgets_project_uniq
    ON public.budgets(user_id, project_id, month, year)
    WHERE project_id IS NOT NULL;

-- Index for fast lookups in notification scheduler
CREATE INDEX IF NOT EXISTS budgets_notify_idx
    ON public.budgets(month, year, notify_enabled)
    WHERE notify_enabled = TRUE;
