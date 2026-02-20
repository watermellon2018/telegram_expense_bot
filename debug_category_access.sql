-- Debug: Check category access for invited user
-- Replace with your actual values:
-- User ID: 1369264761 (invited user)
-- Category ID: 60 (продукты)
-- Owner ID: 400564356

-- 1. Check category details
SELECT 
    category_id,
    name,
    user_id as created_by,
    project_id,
    is_system,
    is_active
FROM categories
WHERE category_id = 60;

-- 2. Check if invited user is a project member
SELECT 
    p.project_id,
    p.project_name,
    p.user_id as owner_id,
    pm.user_id as member_id,
    pm.role
FROM projects p
LEFT JOIN project_members pm ON p.project_id = pm.project_id
WHERE p.project_id = (SELECT project_id FROM categories WHERE category_id = 60)
  AND p.is_active = TRUE;

-- 3. Test the exact query from get_category_by_id for invited user
SELECT c.category_id, c.name, c.is_system, c.is_active, c.project_id, c.created_at
FROM categories c
WHERE c.category_id = 60
  AND c.is_active = TRUE
  AND (
      c.user_id = '1369264761'  -- User owns the category
      OR c.project_id IS NULL  -- Global category (accessible to all)
      OR EXISTS (
          -- User is a member of the category's project
          SELECT 1 FROM projects p
          LEFT JOIN project_members pm ON p.project_id = pm.project_id AND pm.user_id = '1369264761'
          WHERE p.project_id = c.project_id
            AND p.is_active = TRUE
            AND (p.user_id = '1369264761' OR pm.user_id = '1369264761')
      )
  );

-- 4. Check project membership directly
SELECT 
    CASE 
        WHEN p.user_id = '1369264761' THEN 'Owner'
        WHEN pm.user_id = '1369264761' THEN 'Member (' || pm.role || ')'
        ELSE 'Not a member'
    END as membership_status
FROM projects p
LEFT JOIN project_members pm ON p.project_id = pm.project_id AND pm.user_id = '1369264761'
WHERE p.project_id = (SELECT project_id FROM categories WHERE category_id = 60)
  AND p.is_active = TRUE;

-- Expected result:
-- If user is a member, query 3 should return the category
-- If query 3 returns nothing, the user doesn't have access
