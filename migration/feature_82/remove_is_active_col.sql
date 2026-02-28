-- 1. Проверка потенциальной рассинхронизации
-- Если есть строки с неконсистентным состоянием, их стоит исправить вручную
SELECT project_id, is_active, deleted_at
FROM public.projects
WHERE (is_active = true AND deleted_at IS NOT NULL)
   OR (is_active = false AND deleted_at IS NULL);

-- 2. Синхронизация данных перед удалением колонки
-- Установим deleted_at для старых удалённых проектов, если вдруг NULL
UPDATE public.projects
SET deleted_at = now()
WHERE is_active = false
  AND deleted_at IS NULL;

-- Обнуляем deleted_at для проектов, помеченных как активные
UPDATE public.projects
SET deleted_at = NULL
WHERE is_active = true
  AND deleted_at IS NOT NULL;

-- 3. Удаляем колонку is_active
ALTER TABLE public.projects
DROP COLUMN IF EXISTS is_active;
