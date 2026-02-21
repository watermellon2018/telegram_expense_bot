-- Migration Script: Add Multi-User Project Support
-- This script prepares existing data for shared projects feature

-- Part 1: Add project owners to project_members table
-- This ensures all existing project owners are also members

INSERT INTO project_members (project_id, user_id, role, joined_at)
SELECT 
    project_id, 
    user_id, 
    'owner', 
    COALESCE(created_date::timestamp, NOW())
FROM projects
WHERE is_active = TRUE
ON CONFLICT (project_id, user_id) DO NOTHING;

-- Part 2: Verify and fix invalid active_project_id references
-- Users should only have active_project_id set if they have access to that project

-- First, identify users with invalid active_project_id
SELECT 
    u.user_id,
    u.active_project_id,
    p.project_name,
    CASE 
        WHEN p.project_id IS NULL THEN 'Project does not exist'
        WHEN p.user_id = u.user_id THEN 'OK (owner)'
        WHEN pm.user_id IS NOT NULL THEN 'OK (member)'
        ELSE 'Invalid (no access)'
    END as status
FROM users u
LEFT JOIN projects p ON u.active_project_id = p.project_id
LEFT JOIN project_members pm ON u.active_project_id = pm.project_id AND pm.user_id = u.user_id
WHERE u.active_project_id IS NOT NULL
ORDER BY status, u.user_id;

-- Reset invalid active_project_id (users without access)
UPDATE users u
SET active_project_id = NULL
WHERE active_project_id IS NOT NULL
  AND NOT EXISTS (
    SELECT 1 
    FROM projects p
    LEFT JOIN project_members pm ON p.project_id = pm.project_id AND pm.user_id = u.user_id
    WHERE p.project_id = u.active_project_id
      AND p.is_active = TRUE
      AND (p.user_id = u.user_id OR pm.user_id = u.user_id)
  );

-- Part 3: Create recommended indexes for performance

-- Index for project member lookups
CREATE INDEX IF NOT EXISTS idx_project_members_user_id 
ON project_members(user_id);

-- Index for project member + project lookups
CREATE INDEX IF NOT EXISTS idx_project_members_project_user 
ON project_members(project_id, user_id);

-- Index for expenses by project (for aggregation queries)
CREATE INDEX IF NOT EXISTS idx_expenses_project_id 
ON expenses(project_id) 
WHERE project_id IS NOT NULL;

-- Index for expenses by project and month (for monthly stats)
CREATE INDEX IF NOT EXISTS idx_expenses_project_month 
ON expenses(project_id, month) 
WHERE project_id IS NOT NULL;

-- Index for categories by project
CREATE INDEX IF NOT EXISTS idx_categories_project_id 
ON categories(project_id) 
WHERE project_id IS NOT NULL;

-- Index for invites by expiration (for cleanup)
CREATE INDEX IF NOT EXISTS idx_invites_expires_at 
ON project_invites(expires_at);

-- Part 4: Validation queries - run these to verify migration success

-- Count projects with owners in project_members
SELECT 
    COUNT(*) as total_projects,
    COUNT(DISTINCT pm.project_id) as projects_with_owner_membership
FROM projects p
LEFT JOIN project_members pm ON p.project_id = pm.project_id AND p.user_id = pm.user_id
WHERE p.is_active = TRUE;

-- Count users with valid active_project_id
SELECT 
    COUNT(*) as users_with_active_project,
    SUM(CASE 
        WHEN EXISTS (
            SELECT 1 FROM projects pr
            LEFT JOIN project_members pm2 ON pr.project_id = pm2.project_id AND pm2.user_id = u.user_id
            WHERE pr.project_id = u.active_project_id 
              AND (pr.user_id = u.user_id OR pm2.user_id = u.user_id)
        ) THEN 1 ELSE 0 
    END) as valid_active_projects,
    SUM(CASE 
        WHEN NOT EXISTS (
            SELECT 1 FROM projects pr
            LEFT JOIN project_members pm2 ON pr.project_id = pm2.project_id AND pm2.user_id = u.user_id
            WHERE pr.project_id = u.active_project_id 
              AND (pr.user_id = u.user_id OR pm2.user_id = u.user_id)
        ) THEN 1 ELSE 0 
    END) as invalid_active_projects
FROM users u
WHERE u.active_project_id IS NOT NULL;

-- Show project membership summary
SELECT 
    p.project_id,
    p.project_name,
    p.user_id as owner_id,
    COUNT(pm.user_id) as member_count,
    STRING_AGG(pm.user_id || ' (' || pm.role || ')', ', ' ORDER BY pm.role DESC, pm.user_id) as members
FROM projects p
LEFT JOIN project_members pm ON p.project_id = pm.project_id
WHERE p.is_active = TRUE
GROUP BY p.project_id, p.project_name, p.user_id
ORDER BY p.project_id;

-- Show expenses by project and user (to verify multi-user tracking)
SELECT 
    p.project_name,
    e.user_id,
    COUNT(*) as expense_count,
    SUM(e.amount) as total_amount
FROM expenses e
JOIN projects p ON e.project_id = p.project_id
WHERE e.project_id IS NOT NULL
GROUP BY p.project_name, e.user_id
ORDER BY p.project_name, e.user_id;

-- Migration complete!
-- Next steps:
-- 1. Test project access with existing projects
-- 2. Test adding expenses as project owner
-- 3. Add a new member to a project (manual INSERT into project_members)
-- 4. Verify new member can see all expenses
