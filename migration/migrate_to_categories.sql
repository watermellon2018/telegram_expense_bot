BEGIN;

-- Шаг 1: Создание таблицы категорий
CREATE TABLE IF NOT EXISTS categories (
    category_id SERIAL PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    project_id INTEGER, -- Убрал FK здесь, так как он составной в вашей схеме
    name VARCHAR(255) NOT NULL,
    is_system BOOLEAN NOT NULL DEFAULT FALSE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Важно: Исправляем FOREIGN KEY для проектов, так как в таблице projects PK — это (project_id, user_id)
ALTER TABLE categories 
ADD CONSTRAINT categories_project_fkey 
FOREIGN KEY (project_id, user_id) REFERENCES projects(project_id, user_id) ON DELETE CASCADE;

-- Решение проблемы с LOWER(name): Создаем уникальный индекс вместо CONSTRAINT
CREATE UNIQUE INDEX IF NOT EXISTS categories_user_project_name_lower_idx 
ON categories (user_id, COALESCE(project_id, -1), LOWER(name));

-- Шаг 2: Индексы для производительности
CREATE INDEX IF NOT EXISTS idx_categories_user_id ON categories(user_id);
CREATE INDEX IF NOT EXISTS idx_categories_project_id ON categories(project_id);

-- Шаг 3: Добавление category_id в expenses
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

-- Шаг 4: Миграция дефолтных категорий
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
        -- На всякий случай проверяем юзера
        INSERT INTO users(user_id) VALUES(user_record.user_id) ON CONFLICT (user_id) DO NOTHING;
        
        FOREACH cat_name IN ARRAY default_cats LOOP
            -- Используем INSERT без ON CONFLICT для простоты миграции, проверяя наличие через EXISTS
            IF NOT EXISTS (
                SELECT 1 FROM categories 
                WHERE user_id = user_record.user_id 
                  AND project_id IS NULL 
                  AND LOWER(name) = LOWER(cat_name)
            ) THEN
                INSERT INTO categories(user_id, project_id, name, is_system, is_active)
                VALUES(user_record.user_id, NULL, cat_name, TRUE, TRUE);
            END IF;
        END LOOP;
    END LOOP;
END $$;

-- Шаг 5: Обновление category_id в expenses
UPDATE expenses e
SET category_id = c.category_id
FROM categories c
WHERE e.user_id = c.user_id
  AND (e.project_id IS NULL AND c.project_id IS NULL OR e.project_id = c.project_id)
  AND LOWER(e.category) = LOWER(c.name)
  AND e.category_id IS NULL;

-- Шаг 6: Создание категорий, которых нет в списке дефолтных
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
        -- Проверяем, не создали ли мы такую категорию на предыдущем шаге цикла
        SELECT category_id INTO new_id FROM categories 
        WHERE user_id = expense_record.user_id 
          AND (project_id IS NULL AND expense_record.project_id IS NULL OR project_id = expense_record.project_id)
          AND LOWER(name) = LOWER(expense_record.category);

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

-- Шаг 7: Проверка
DO $$
DECLARE
    missing_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO missing_count FROM expenses WHERE category_id IS NULL;
    IF missing_count > 0 THEN
        RAISE EXCEPTION 'Миграция провалена: % записей без категории', missing_count;
    END IF;
END $$;

-- Шаг 8: Запрет NULL
ALTER TABLE expenses ALTER COLUMN category_id SET NOT NULL;

COMMIT;