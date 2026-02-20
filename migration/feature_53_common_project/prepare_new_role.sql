-- 1. Добавляем временную колонку в таблицу проектов
ALTER TABLE public.projects ADD COLUMN IF NOT EXISTS global_project_id SERIAL;

-- 2. Создаем таблицу участников (связующее звено)
CREATE TABLE IF NOT EXISTS public.project_members (
    project_id integer NOT NULL,
    user_id text NOT NULL,
    role character varying(20) NOT NULL DEFAULT 'member', -- owner, editor, viewer
    joined_at timestamp without time zone DEFAULT now(),
    CONSTRAINT project_members_pkey PRIMARY KEY (project_id, user_id),
    CONSTRAINT fk_user FOREIGN KEY (user_id) REFERENCES public.users (user_id) ON DELETE CASCADE
);

-- 3. Переносим текущих владельцев в таблицу участников
-- Все, кто сейчас в таблице projects, становятся владельцами (owner) этих проектов
INSERT INTO public.project_members (project_id, user_id, role)
SELECT global_project_id, user_id, 'owner' FROM public.projects;