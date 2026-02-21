-- Verify and fix user membership in projects
-- Replace user_id with your invited user ID: 1369264761

-- 1. Check if user is in project_members for project 4
SELECT 
    pm.project_id,
    p.project_name,
    pm.user_id,
    pm.role,
    pm.joined_at
FROM project_members pm
JOIN projects p ON pm.project_id = p.project_id
WHERE pm.user_id = '1369264761'
  AND pm.project_id = 4;

-- 2. Check all projects user is member of
SELECT 
    pm.project_id,
    p.project_name,
    pm.role,
    pm.joined_at
FROM project_members pm
JOIN projects p ON pm.project_id = p.project_id
WHERE pm.user_id = '1369264761'
ORDER BY pm.project_id;

-- 3. Check if user has active_project_id set
SELECT 
    user_id,
    active_project_id,
    (SELECT project_name FROM projects WHERE project_id = active_project_id) as active_project_name
FROM users
WHERE user_id = '1369264761';

-- 4. Check project 4 details
SELECT 
    project_id,
    project_name,
    user_id as owner_id,
    is_active
FROM projects
WHERE project_id = 4;

-- 5. If user is NOT in project_members but should be, add them:
-- UNCOMMENT TO FIX:
/*
INSERT INTO project_members (project_id, user_id, role, joined_at)
VALUES (4, '1369264761', 'editor', NOW())
ON CONFLICT (project_id, user_id) DO UPDATE
SET role = EXCLUDED.role;
*/

-- 6. Verify the fix worked
SELECT 
    pm.project_id,
    p.project_name,
    pm.user_id,
    pm.role,
    CASE 
        WHEN p.user_id = pm.user_id THEN 'Owner'
        WHEN pm.role = 'editor' THEN 'Editor (can add expenses)'
        WHEN pm.role = 'viewer' THEN 'Viewer (read-only)'
        ELSE 'Unknown'
    END as access_level
FROM project_members pm
JOIN projects p ON pm.project_id = p.project_id
WHERE pm.user_id = '1369264761'
  AND pm.project_id = 4;
