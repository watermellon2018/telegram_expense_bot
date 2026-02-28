-- 3. Создаём partial index для очистки
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_projects_deleted_cleanup
ON public.projects (deleted_at)
WHERE deleted_at IS NOT NULL;
