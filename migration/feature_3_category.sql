-- Сброс состояния после предыдущих ошибок
ROLLBACK;

BEGIN;

-- 1. Создание таблицы категорий
CREATE TABLE IF NOT EXISTS categories (
    category_id SERIAL PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    project_id INTEGER, 
    name VARCHAR(255) NOT NULL,
    is_system BOOLEAN NOT NULL DEFAULT FALSE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 2. Добавление составного Foreign Key для проектов
-- Используем IF NOT EXISTS логику через DO блок, чтобы избежать ошибок при повторном запуске
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'categories_project_fkey') THEN
        ALTER TABLE categories 
        ADD CONSTRAINT categories_project_fkey 
        FOREIGN KEY (project_id, user_id) REFERENCES projects(project_id, user_id) ON DELETE CASCADE;
    END IF;
END $$;

-- 3. Создание УНИКАЛЬНОГО индекса (сразу с учетом фильтра is_active)
-- Позволяет иметь одинаковые названия, если старые категории удалены (is_active = false)
DROP INDEX IF EXISTS categories_user_project_name_lower_idx;
CREATE UNIQUE INDEX categories_user_project_name_lower_idx 
ON categories (user_id, COALESCE(project_id, -1), LOWER(name))
WHERE is_active = TRUE;

-- 4. Дополнительные индексы для скорости
CREATE INDEX IF NOT EXISTS idx_categories_user_id ON categories(user_id);
CREATE INDEX IF NOT EXISTS idx_categories_project_id ON categories(project_id);

-- 5. Подготовка таблицы expenses
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'expenses' AND column_name = 'category_id'
    ) THEN
        ALTER TABLE expenses ADD COLUMN category_id INTEGER REFERENCES categories(category_id) ON DELETE RESTRICT;
        CREATE INDEX IF NOT EXISTS idx_expenses_category_id ON expenses(category_id);
    END IF;
END $$;

-- 6. Наполнение дефолтными системными категориями
DO $$
DECLARE
    user_record RECORD;
    cat_name TEXT;
    default_cats TEXT[] := ARRAY[
        'продукты', 'транспорт', 'развлечения', 'рестораны', 'здоровье',
        'одежда', 'связь', 'образование', 'спорт', 'дом',
        'инвестиции', 'маркетплейсы', 'красота', 'животные', 'подписки',
        'кредиты', 'налоги', 'отпуск', 'подарки', 'прочее'
    ];
BEGIN
    FOR user_record IN SELECT DISTINCT user_id FROM expenses LOOP
        -- Гарантируем наличие пользователя в таблице users
        INSERT INTO users(user_id) VALUES(user_record.user_id) ON CONFLICT (user_id) DO NOTHING;
        
        FOREACH cat_name IN ARRAY default_cats LOOP
            IF NOT EXISTS (
                SELECT 1 FROM categories 
                WHERE user_id = user_record.user_id 
                  AND project_id IS NULL 
                  AND LOWER(name) = LOWER(cat_name)
                  AND is_active = TRUE
            ) THEN
                INSERT INTO categories(user_id, project_id, name, is_system, is_active)
                VALUES(user_record.user_id, NULL, cat_name, TRUE, TRUE);
            END IF;
        END LOOP;
    END LOOP;
END $$;

-- 7. Привязка существующих расходов к новым ID категорий
UPDATE expenses e
SET category_id = c.category_id
FROM categories c
WHERE e.user_id = c.user_id
  AND (e.project_id IS NULL AND c.project_id IS NULL OR e.project_id = c.project_id)
  AND LOWER(e.category) = LOWER(c.name)
  AND c.is_active = TRUE
  AND e.category_id IS NULL;

-- 8. Создание кастомных категорий, которых не было в списке дефолтных
DO $$
DECLARE
    expense_record RECORD;
    new_id INTEGER;
BEGIN
    FOR expense_record IN 
        SELECT DISTINCT user_id, project_id, category
        FROM expenses 
        WHERE category_id IS NULL AND category IS NOT NULL
    LOOP
        -- Проверка на существование
        SELECT category_id INTO new_id FROM categories 
        WHERE user_id = expense_record.user_id 
          AND (project_id IS NULL AND expense_record.project_id IS NULL OR project_id = expense_record.project_id)
          AND LOWER(name) = LOWER(expense_record.category)
          AND is_active = TRUE;

        IF new_id IS NULL THEN
            INSERT INTO categories(user_id, project_id, name, is_system, is_active)
            VALUES(expense_record.user_id, expense_record.project_id, expense_record.category, FALSE, TRUE)
            RETURNING category_id INTO new_id;
        END IF;

        UPDATE expenses
        SET category_id = new_id
        WHERE user_id = expense_record.user_id
          AND (project_id IS NULL AND expense_record.project_id IS NULL OR project_id = expense_record.project_id)
          AND LOWER(category) = LOWER(expense_record.category)
          AND category_id IS NULL;
    END LOOP;
END $$;

-- 9. Финальная проверка и установка NOT NULL
DO $$
DECLARE
    missing_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO missing_count FROM expenses WHERE category_id IS NULL;
    IF missing_count > 0 THEN
        RAISE EXCEPTION 'Миграция провалена: % записей без категории', missing_count;
    END IF;
END $$;

ALTER TABLE expenses ALTER COLUMN category_id SET NOT NULL;

COMMIT;