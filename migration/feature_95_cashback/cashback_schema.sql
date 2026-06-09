BEGIN;

CREATE TABLE IF NOT EXISTS public.user_cards (
    id SERIAL PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES public.users(user_id) ON DELETE CASCADE,
    card_name VARCHAR(255) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
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
    ON public.user_cards(user_id);

CREATE TABLE IF NOT EXISTS public.cashback_categories (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    is_global BOOLEAN NOT NULL DEFAULT FALSE,
    user_id TEXT NULL REFERENCES public.users(user_id) ON DELETE CASCADE,
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
    ON public.cashback_categories(user_id);

CREATE TABLE IF NOT EXISTS public.user_cashback_rules (
    id SERIAL PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES public.users(user_id) ON DELETE CASCADE,
    user_card_id INTEGER NOT NULL REFERENCES public.user_cards(id) ON DELETE RESTRICT,
    cashback_category_id INTEGER NOT NULL REFERENCES public.cashback_categories(id) ON DELETE RESTRICT,
    year INTEGER NOT NULL CHECK (year BETWEEN 2000 AND 2100),
    month INTEGER NOT NULL CHECK (month BETWEEN 1 AND 12),
    percent NUMERIC(5, 2) NOT NULL CHECK (percent >= 0 AND percent <= 100),
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_user_cashback_rule_month UNIQUE (user_card_id, cashback_category_id, year, month)
);

CREATE INDEX IF NOT EXISTS idx_user_cashback_rules_user_month
    ON public.user_cashback_rules(user_id, year, month);

CREATE INDEX IF NOT EXISTS idx_user_cashback_rules_card
    ON public.user_cashback_rules(user_card_id);

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

COMMIT;
