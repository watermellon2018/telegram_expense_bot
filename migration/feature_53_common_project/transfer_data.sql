-- 1. Создаем записи "Основной проект" для тех, у кого были траты с NULL
-- Это гарантирует, что у каждой траты будет свой реальный проект
INSERT INTO public.projects (project_id, user_id, project_name, is_active)
SELECT DISTINCT -1, user_id, 'Основной', true
FROM public.users u
WHERE NOT EXISTS (
    SELECT 1 FROM public.projects p WHERE p.user_id = u.user_id AND (p.project_name = 'Основной' OR p.project_id = -1)
);

-- 2. Добавляем временные колонки для новых связей
ALTER TABLE public.categories ADD COLUMN IF NOT EXISTS new_project_id integer;
ALTER TABLE public.expenses ADD COLUMN IF NOT EXISTS new_project_id integer;
ALTER TABLE public.users ADD COLUMN IF NOT EXISTS new_active_project_id integer;

-- 3. Обновляем категории (учитывая старый NULL через COALESCE)
UPDATE public.categories c
SET new_project_id = p.global_project_id
FROM public.projects p
WHERE c.user_id = p.user_id 
  AND COALESCE(c.project_id, -1) = p.project_id;

-- 4. Обновляем расходы
UPDATE public.expenses e
SET new_project_id = p.global_project_id
FROM public.projects p
WHERE e.user_id = p.user_id 
  AND COALESCE(e.project_id, -1) = p.project_id;

-- 5. Обновляем текущий активный проект пользователя
UPDATE public.users u
SET new_active_project_id = p.global_project_id
FROM public.projects p
WHERE u.user_id = p.user_id 
  AND COALESCE(u.active_project_id, -1) = p.project_id;