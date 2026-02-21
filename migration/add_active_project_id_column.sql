-- Add active_project_id column to users table if it doesn't exist
-- This column stores the currently active project ID for each user
-- NULL means the user is using general expenses (not a specific project)

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'users' AND column_name = 'active_project_id'
    ) THEN
        ALTER TABLE users
        ADD COLUMN active_project_id INTEGER;
        
        RAISE NOTICE 'Column active_project_id added to users table';
    ELSE
        RAISE NOTICE 'Column active_project_id already exists in users table';
    END IF;
END $$;


