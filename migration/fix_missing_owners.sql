-- Fix: Add missing project owners to project_members table
-- This ensures all project owners have proper permissions

-- Check which owners are missing from project_members
SELECT 
    p.project_id,
    p.project_name,
    p.user_id as owner_id,
    CASE WHEN pm.user_id IS NULL THEN 'MISSING' ELSE 'OK' END as status
FROM projects p
LEFT JOIN project_members pm ON p.project_id = pm.project_id AND p.user_id = pm.user_id
WHERE p.is_active = TRUE
ORDER BY status DESC, p.project_id;

-- Add all missing owners to project_members
INSERT INTO project_members (project_id, user_id, role, joined_at)
SELECT 
    p.project_id,
    p.user_id,
    'owner',
    COALESCE(p.created_date::timestamp, NOW())
FROM projects p
WHERE p.is_active = TRUE
  AND NOT EXISTS (
      SELECT 1 
      FROM project_members pm 
      WHERE pm.project_id = p.project_id 
        AND pm.user_id = p.user_id
  )
ON CONFLICT (project_id, user_id) DO NOTHING;

-- Verify all owners are now in project_members
SELECT 
    COUNT(*) as total_active_projects,
    SUM(CASE WHEN pm.user_id IS NOT NULL THEN 1 ELSE 0 END) as owners_in_members,
    SUM(CASE WHEN pm.user_id IS NULL THEN 1 ELSE 0 END) as owners_missing
FROM projects p
LEFT JOIN project_members pm ON p.project_id = pm.project_id AND p.user_id = pm.user_id
WHERE p.is_active = TRUE;

-- Should show 0 owners_missing if successful
