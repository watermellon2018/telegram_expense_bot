# Multi-User Project Refactoring - Implementation Summary

## Overview
The backend has been refactored to support shared projects where multiple users can collaborate on expense tracking. All database queries now properly filter by `project_id` and validate user access to projects.

## Key Changes

### 1. **utils/projects.py** - Project Access Control

#### New Behavior:
- **`get_all_projects()`** - Returns ALL projects user has access to (owned OR member)
- **`get_project_by_id()`** - Validates user is owner or member before returning
- **`get_project_by_name()`** - Validates user access
- **`set_active_project()`** - Validates user has access before setting active

#### New Functions:
- **`is_project_member(user_id, project_id)`** - Check if user has access to project
- **`get_user_role_in_project(user_id, project_id)`** - Returns 'owner', 'editor', 'viewer', or None
- **`get_project_members(project_id)`** - Returns all members of a project including owner

#### Project Creation:
- Owner is now added to `project_members` table for consistency
- Makes queries simpler since all access is tracked in one place

#### Project Deletion:
- Only project owner can delete
- Deletes ALL members' expenses, not just owner's
- Cleans up `project_members` table
- Resets `active_project_id` for all affected users

### 2. **utils/excel.py** - Multi-User Expense Queries

#### Critical Change: Shared Project Data Visibility
**For projects (project_id != NULL):**
- Shows expenses from **ALL project members**
- Statistics aggregate all members' data
- Budget tracking shows total project spend

**For personal expenses (project_id == NULL):**
- Shows only the user's own expenses
- Statistics show only personal data

#### Updated Functions:
- **`get_month_expenses()`** - Shows all members' expenses for projects
- **`get_category_expenses()`** - Shows all members' expenses for projects
- **`get_all_expenses()`** - Shows all members' expenses for projects (includes `user_id` column)
- **`get_day_expenses()`** - Shows all members' expenses for projects
- **`set_budget()`** - Validates project access; budget is per-user but actual shows total

#### Access Validation:
All query functions now validate that `user_id` has access to `project_id` before returning data.

### 3. **utils/categories.py** - Shared Category Management

#### New Behavior:
**For projects:**
- Returns categories created by ANY project member
- Categories are visible to all project members
- Category deletion transfers ALL members' expenses

**For personal:**
- Returns only user's own global categories

#### Updated Functions:
- **`get_categories_for_user_project()`** - Shows all project members' categories
- **`delete_category_with_transfer()`** - Transfers all members' expenses in projects
- **`deactivate_category()`** - Checks if ANY member is using the category

### 4. **utils/visualization.py** - No Changes Needed
Already passes `project_id` correctly to data functions, so automatically shows correct multi-user data.

## Database Schema Notes

### Key Tables:
```sql
-- Users with active project tracking
users (
  user_id TEXT PRIMARY KEY,
  active_project_id INTEGER REFERENCES projects(project_id)
)

-- Projects (owner stored here)
projects (
  project_id INTEGER PRIMARY KEY,
  user_id TEXT REFERENCES users(user_id),  -- Owner
  project_name TEXT,
  is_active BOOLEAN
)

-- Project membership (includes roles)
project_members (
  project_id INTEGER REFERENCES projects(project_id),
  user_id TEXT REFERENCES users(user_id),
  role VARCHAR(20),  -- 'owner', 'editor', 'viewer'
  joined_at TIMESTAMP,
  PRIMARY KEY (project_id, user_id)
)

-- Expenses track both project and individual user
expenses (
  id INTEGER PRIMARY KEY,
  user_id TEXT REFERENCES users(user_id),      -- Who added this expense
  project_id INTEGER REFERENCES projects(project_id),  -- Which project
  category_id INTEGER REFERENCES categories(category_id),
  amount NUMERIC,
  date DATE,
  description TEXT
)

-- Categories can be global (project_id=NULL) or project-specific
categories (
  category_id INTEGER PRIMARY KEY,
  user_id TEXT REFERENCES users(user_id),     -- Who created this category
  project_id INTEGER REFERENCES projects(project_id),  -- NULL for global
  name VARCHAR(255),
  is_system BOOLEAN,
  is_active BOOLEAN
)
```

## Important Implementation Details

### 1. Expense Tracking
When adding an expense:
- `user_id` = the user who added the expense (for attribution)
- `project_id` = the active project (from `users.active_project_id`)
- All project members can see this expense

### 2. Category Visibility
- Global categories (project_id=NULL): only visible to creator
- Project categories (project_id=X): visible to all project members
- System categories: always visible

### 3. Budget Tracking
- Each user can set their own budget for a project
- The "actual" field shows total project spending (all members)
- This allows each member to track against their personal budget while seeing total spend

### 4. Access Control Pattern
```python
# Check access before showing project data
if project_id is not None:
    if not await projects.is_project_member(user_id, project_id):
        return []  # or appropriate empty response
```

## Testing Checklist

### Phase 1: Single User (Backwards Compatibility)
- [ ] Create personal expense (project_id=NULL)
- [ ] View monthly stats for personal expenses
- [ ] Create personal category
- [ ] Delete personal category
- [ ] Export personal expenses

### Phase 2: Project Owner
- [ ] Create new project
- [ ] Add expense to project
- [ ] View project stats
- [ ] Create project-specific category
- [ ] Switch between personal and project expenses
- [ ] Delete project (verify cascades)

### Phase 3: Multi-User Collaboration
- [ ] User A creates project
- [ ] User B joins project (via project_members insert)
- [ ] User B adds expense to project
- [ ] User A sees User B's expense in stats
- [ ] Both users see combined expense totals
- [ ] User B creates category in project
- [ ] User A can use User B's category
- [ ] User A (owner) deletes category - transfers both users' expenses

### Phase 4: Access Control
- [ ] User C (not a member) cannot see project stats
- [ ] User C cannot set project as active
- [ ] Only owner can delete project
- [ ] Member can add expenses but not delete project

## Migration Considerations

### For Existing Data:
If you have existing projects in the database:

1. **Add owners to project_members:**
```sql
INSERT INTO project_members (project_id, user_id, role, joined_at)
SELECT project_id, user_id, 'owner', created_date
FROM projects
WHERE is_active = TRUE
ON CONFLICT (project_id, user_id) DO NOTHING;
```

2. **Verify active_project_id validity:**
```sql
-- Find users with invalid active_project_id
SELECT u.user_id, u.active_project_id
FROM users u
LEFT JOIN projects p ON u.active_project_id = p.project_id
LEFT JOIN project_members pm ON u.active_project_id = pm.project_id AND pm.user_id = u.user_id
WHERE u.active_project_id IS NOT NULL
  AND (p.project_id IS NULL OR (p.user_id != u.user_id AND pm.user_id IS NULL));

-- Reset invalid active_project_id
UPDATE users u
SET active_project_id = NULL
WHERE active_project_id IS NOT NULL
  AND NOT EXISTS (
    SELECT 1 FROM projects p
    LEFT JOIN project_members pm ON p.project_id = pm.project_id AND pm.user_id = u.user_id
    WHERE p.project_id = u.active_project_id
      AND (p.user_id = u.user_id OR pm.user_id = u.user_id)
  );
```

## API Changes Summary

### Changed Return Types:
```python
# get_project_by_id() now returns:
{
    'project_id': int,
    'project_name': str,
    'created_date': str,
    'is_active': bool,
    'owner_id': str,        # NEW
    'role': str,            # NEW: 'owner', 'editor', 'viewer'
    'is_owner': bool,       # NEW: True if user is owner
}

# get_all_projects() returns list of above dicts

# get_all_expenses() now includes:
{
    ...,
    'user_id': str,  # NEW: Shows which user added each expense
}
```

### New Functions:
- `projects.is_project_member(user_id, project_id) -> bool`
- `projects.get_user_role_in_project(user_id, project_id) -> str|None`
- `projects.get_project_members(project_id) -> list`

## Performance Notes

### Optimized Queries:
- All project access checks use `LEFT JOIN project_members` for single-query validation
- Indexes recommended:
  ```sql
  CREATE INDEX idx_project_members_user ON project_members(user_id);
  CREATE INDEX idx_expenses_project ON expenses(project_id);
  CREATE INDEX idx_categories_project ON categories(project_id);
  ```

## Next Steps for Handlers

The handler files (handlers/*.py) don't need major changes since they already use:
- `context.user_data.get('active_project_id')` for project context
- `excel.add_expense()` with project_id parameter
- `categories.get_categories_for_user_project()` with project_id

However, consider adding:
1. **Project invitation handlers** - for inviting users via invite tokens
2. **Project member management** - viewing/removing members
3. **Role-based actions** - restricting certain actions to owners/editors

## Security Considerations

✅ **Implemented:**
- All queries validate user has access to project before showing data
- Only project owner can delete project
- Users can only delete categories they created
- Active project validation on setting

⚠️ **TODO (if needed):**
- Role-based write permissions (currently all members can add expenses)
- Audit log for who added/modified what
- Rate limiting on project operations
