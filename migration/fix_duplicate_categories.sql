-- Fix: Find and optionally clean duplicate categories
-- This shows categories with the same name in different scopes (global vs project)

-- 1. Show duplicate category names (same name, different project_id)
SELECT 
    LOWER(name) as category_name,
    COUNT(*) as occurrences,
    STRING_AGG(category_id::text || ' (pid: ' || COALESCE(project_id::text, 'NULL') || ', sys: ' || is_system::text || ')', ', ' ORDER BY project_id NULLS LAST) as instances
FROM categories
WHERE is_active = TRUE
GROUP BY LOWER(name)
HAVING COUNT(*) > 1
ORDER BY COUNT(*) DESC, LOWER(name);

-- 2. Show detailed view of duplicates
SELECT 
    c.category_id,
    c.name,
    c.is_system,
    c.project_id,
    CASE 
        WHEN c.project_id IS NULL THEN 'Global'
        ELSE 'Project ' || c.project_id::text
    END as scope,
    c.user_id,
    c.created_at,
    (SELECT COUNT(*) FROM expenses e WHERE e.category_id = c.category_id) as expense_count
FROM categories c
WHERE c.is_active = TRUE
  AND LOWER(c.name) IN (
      SELECT LOWER(name)
      FROM categories
      WHERE is_active = TRUE
      GROUP BY LOWER(name)
      HAVING COUNT(*) > 1
  )
ORDER BY LOWER(c.name), c.project_id NULLS LAST;

-- 3. OPTIONAL: Remove duplicate global categories if project-specific ones exist
-- UNCOMMENT ONLY IF YOU WANT TO DELETE GLOBAL DUPLICATES:
/*
-- This will keep project-specific categories and remove their global duplicates
DELETE FROM categories c1
WHERE c1.is_active = TRUE
  AND c1.project_id IS NULL  -- Only delete global categories
  AND c1.is_system = FALSE    -- Only delete non-system categories
  AND EXISTS (
      -- Check if a project-specific version exists
      SELECT 1 
      FROM categories c2
      WHERE c2.is_active = TRUE
        AND c2.project_id IS NOT NULL
        AND LOWER(c2.name) = LOWER(c1.name)
  )
  AND NOT EXISTS (
      -- Don't delete if expenses reference this category
      SELECT 1 FROM expenses e WHERE e.category_id = c1.category_id
  );

-- Show what was deleted
SELECT 'Deleted ' || COUNT(*) || ' duplicate global categories' as result
FROM categories
WHERE is_active = FALSE;
*/

-- 4. OPTIONAL: Deactivate instead of delete (safer)
-- UNCOMMENT TO DEACTIVATE DUPLICATES:
/*
UPDATE categories c1
SET is_active = FALSE
WHERE c1.is_active = TRUE
  AND c1.project_id IS NULL  -- Only deactivate global categories
  AND c1.is_system = FALSE    -- Only deactivate non-system categories
  AND EXISTS (
      -- Check if a project-specific version exists
      SELECT 1 
      FROM categories c2
      WHERE c2.is_active = TRUE
        AND c2.project_id IS NOT NULL
        AND LOWER(c2.name) = LOWER(c1.name)
  )
  AND NOT EXISTS (
      -- Don't deactivate if expenses reference this category
      SELECT 1 FROM expenses e WHERE e.category_id = c1.category_id
  );

-- Show results
SELECT 'Deactivated ' || COUNT(*) || ' duplicate global categories' as result
FROM categories
WHERE is_active = FALSE
  AND project_id IS NULL;
*/

-- Note: The code now uses DISTINCT ON to handle duplicates automatically
-- So you don't need to clean the database unless you want to
