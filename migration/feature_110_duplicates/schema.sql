-- Миграция: защита от дубликатов расходов в совместных проектах
-- Ветка: feature_110  (issue #110)
--
-- Что добавляет:
--   1. expenses.created_at   — точное время создания записи (для временного окна дубликатов)
--   2. expenses.deleted_at   — soft delete расхода (NULL = активен)
--   3. project_member_settings — индивидуальные настройки уведомлений участника
--   4. expense_duplicate_reports — отметки «возможный дубликат» с разрешением
--
-- Миграция идемпотентна (IF NOT EXISTS / ADD COLUMN IF NOT EXISTS) и обратима
-- (см. rollback.sql). Не ломает существующие проекты и расходы:
--   - created_at у старых строк backfill-ится из date+time (или now() как fallback);
--   - отсутствие строки в project_member_settings трактуется приложением как режим 'all';
--   - deleted_at по умолчанию NULL — все существующие расходы остаются активными.

BEGIN;

-- =========================================================
-- 1. Расширение таблицы expenses
-- =========================================================

-- Точное время создания записи. Нужно для критерия «расход создан недавно»
-- (временное окно дубликатов). У существующих строк нет этого значения,
-- поэтому backfill ниже.
ALTER TABLE public.expenses
    ADD COLUMN IF NOT EXISTS created_at TIMESTAMP;

-- Soft delete: NULL — расход активен, значение — момент мягкого удаления.
ALTER TABLE public.expenses
    ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMP;

-- Backfill created_at для старых расходов:
--   - если есть date и time — собираем из них;
--   - если только date — берём начало дня;
--   - иначе now().
-- Выполняется один раз: только для строк, где created_at ещё NULL.
UPDATE public.expenses
SET created_at = COALESCE(
        (date + COALESCE("time", time '00:00:00'))::timestamp,
        now()
    )
WHERE created_at IS NULL;

-- После backfill задаём DEFAULT и NOT NULL, чтобы новые ручные вставки
-- (если кто-то вставит без created_at) тоже получали значение.
ALTER TABLE public.expenses
    ALTER COLUMN created_at SET DEFAULT now();

ALTER TABLE public.expenses
    ALTER COLUMN created_at SET NOT NULL;

-- Индекс для поиска потенциальных дубликатов:
-- запросы фильтруют по project_id + category_id + date и берут свежие активные строки.
CREATE INDEX IF NOT EXISTS idx_expenses_duplicate_lookup
    ON public.expenses (project_id, category_id, date, created_at)
    WHERE project_id IS NOT NULL AND deleted_at IS NULL;

-- =========================================================
-- 2. Настройки уведомлений участника проекта
-- =========================================================
-- Одна строка на пару (project_id, user_id). Отсутствие строки = режим 'all'
-- (обратная совместимость для участников, добавленных до этой фичи).
CREATE TABLE IF NOT EXISTS public.project_member_settings (
    id                      SERIAL PRIMARY KEY,

    project_id              INTEGER NOT NULL
                            REFERENCES public.projects(project_id) ON DELETE CASCADE,
    user_id                 TEXT NOT NULL
                            REFERENCES public.users(user_id) ON DELETE CASCADE,

    -- Режим уведомлений о новых расходах:
    --   'all'        — о каждом расходе
    --   'large_only' — только о расходах выше порога
    --   'disabled'   — не уведомлять
    expense_notify_mode     TEXT NOT NULL DEFAULT 'all'
                            CHECK (expense_notify_mode IN ('all', 'large_only', 'disabled')),

    -- Порог для режима 'large_only' (в валюте проекта). NULL для остальных режимов.
    large_expense_threshold NUMERIC
                            CHECK (large_expense_threshold IS NULL OR large_expense_threshold > 0),

    updated_at              TIMESTAMP NOT NULL DEFAULT now(),

    CONSTRAINT uq_project_member_settings UNIQUE (project_id, user_id)
);

-- =========================================================
-- 3. Отметки «возможный дубликат»
-- =========================================================
CREATE TABLE IF NOT EXISTS public.expense_duplicate_reports (
    id                    SERIAL PRIMARY KEY,

    expense_id            INTEGER NOT NULL
                          REFERENCES public.expenses(id) ON DELETE CASCADE,

    -- Кто отметил расход как возможный дубликат
    reported_by_user_id   TEXT NOT NULL
                          REFERENCES public.users(user_id) ON DELETE CASCADE,

    -- Статус обращения:
    --   'open'    — открыто, ожидает решения автора/владельца
    --   'kept'    — решено: расход оставлен
    --   'deleted' — решено: расход удалён
    status                TEXT NOT NULL DEFAULT 'open'
                          CHECK (status IN ('open', 'kept', 'deleted')),

    created_at            TIMESTAMP NOT NULL DEFAULT now(),
    resolved_at           TIMESTAMP,
    resolved_by_user_id   TEXT
                          REFERENCES public.users(user_id) ON DELETE SET NULL,

    -- Один пользователь не может отметить один и тот же расход дважды
    CONSTRAINT uq_expense_report_per_user UNIQUE (expense_id, reported_by_user_id)
);

-- Индекс для выборки всех отметок по расходу
CREATE INDEX IF NOT EXISTS idx_expense_duplicate_reports_expense
    ON public.expense_duplicate_reports (expense_id);

COMMIT;
