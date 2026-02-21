-- Fix: Update unique index to only enforce uniqueness for active categories
-- This allows recreating deleted (deactivated) categories

-- Drop the old index
DROP INDEX IF EXISTS categories_user_project_name_lower_idx;

-- Create a partial unique index that only applies to active categories
CREATE UNIQUE INDEX categories_user_project_name_lower_idx 
ON categories (user_id, COALESCE(project_id, -1), LOWER(name))
WHERE is_active = TRUE;
