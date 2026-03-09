BEGIN;

-- 1. Добавляем колонку deleted_at
ALTER TABLE public.projects
ADD COLUMN deleted_at timestamptz;

-- 2. Заполняем deleted_at для уже удалённых проектов
UPDATE public.projects
SET deleted_at = now()
WHERE is_active = false;

COMMIT;