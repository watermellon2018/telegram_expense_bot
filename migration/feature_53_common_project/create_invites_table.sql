CREATE TABLE IF NOT EXISTS public.project_invites
(
    token text NOT NULL,                -- Уникальный код (UUID или случайная строка)
    project_id integer NOT NULL,        -- К какому проекту привязан
    inviter_id text NOT NULL,           -- Кто создал приглашение (для статистики)
    role character varying(20) DEFAULT 'editor', -- Какую роль получит вошедший
    created_at timestamp without time zone DEFAULT now(),
    expires_at timestamp without time zone NOT NULL, -- Время жизни ссылки
    CONSTRAINT project_invites_pkey PRIMARY KEY (token),
    CONSTRAINT fk_invite_project FOREIGN KEY (project_id) 
        REFERENCES public.projects (project_id) ON DELETE CASCADE,
    CONSTRAINT fk_invite_user FOREIGN KEY (inviter_id) 
        REFERENCES public.users (user_id) ON DELETE CASCADE
);

-- Индекс для быстрой очистки просроченных ссылок
CREATE INDEX IF NOT EXISTS idx_invites_expires_at ON public.project_invites (expires_at);