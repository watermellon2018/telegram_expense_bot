-- 1. Удаляем таблицу budget и старые зависимости
DROP TABLE IF EXISTS public.budget CASCADE;

-- 2. Удаляем старые внешние ключи и первичный ключ проектов (CASCADE уберет зависимости)
ALTER TABLE public.expenses DROP CONSTRAINT IF EXISTS expenses_project_id_user_id_fkey;
ALTER TABLE public.categories DROP CONSTRAINT IF EXISTS categories_project_fkey;
ALTER TABLE public.projects DROP CONSTRAINT IF EXISTS projects_pkey CASCADE;

-- 3. Пересборка таблицы PROJECTS
ALTER TABLE public.projects DROP COLUMN project_id; -- Удаляем старый составной ID
ALTER TABLE public.projects RENAME COLUMN global_project_id TO project_id;
ALTER TABLE public.projects ADD CONSTRAINT projects_pkey PRIMARY KEY (project_id);

-- 4. Пересборка таблицы CATEGORIES
ALTER TABLE public.categories DROP COLUMN project_id;
ALTER TABLE public.categories RENAME COLUMN new_project_id TO project_id;
ALTER TABLE public.categories ADD CONSTRAINT fk_categories_project FOREIGN KEY (project_id) REFERENCES public.projects(project_id) ON DELETE CASCADE;

-- 5. Пересборка таблицы EXPENSES
ALTER TABLE public.expenses DROP COLUMN project_id;
ALTER TABLE public.expenses RENAME COLUMN new_project_id TO project_id;
ALTER TABLE public.expenses ADD CONSTRAINT fk_expenses_project FOREIGN KEY (project_id) REFERENCES public.projects(project_id) ON DELETE CASCADE;

-- 6. Обновляем таблицу USERS
ALTER TABLE public.users DROP COLUMN active_project_id;
ALTER TABLE public.users RENAME COLUMN new_active_project_id TO active_project_id;

-- 7. Финализируем таблицу PROJECT_MEMBERS
ALTER TABLE public.project_members ADD CONSTRAINT fk_project_id FOREIGN KEY (project_id) REFERENCES public.projects(project_id) ON DELETE CASCADE;

-- 8. Создаем новый уникальный индекс для категорий внутри проекта
DROP INDEX IF EXISTS categories_user_project_name_lower_idx;
CREATE UNIQUE INDEX categories_project_name_idx 
ON public.categories (project_id, lower(name)) 
WHERE is_active = true;