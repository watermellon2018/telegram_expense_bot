-- Откат миграции feature_110 (защита от дубликатов расходов)
--
-- ВНИМАНИЕ: откат удаляет настройки уведомлений участников и историю отметок
-- дубликатов. Сами расходы НЕ удаляются. Колонки created_at/deleted_at в expenses
-- удаляются — после отката информация о времени создания и мягком удалении теряется.
--
-- Выполнять только если нужно полностью вернуть схему к состоянию до feature_110.

BEGIN;

-- 1. Таблицы фичи
DROP TABLE IF EXISTS public.expense_duplicate_reports;
DROP TABLE IF EXISTS public.project_member_settings;

-- 2. Индекс и колонки expenses
DROP INDEX IF EXISTS public.idx_expenses_duplicate_lookup;

ALTER TABLE public.expenses
    DROP COLUMN IF EXISTS deleted_at;

ALTER TABLE public.expenses
    DROP COLUMN IF EXISTS created_at;

COMMIT;
