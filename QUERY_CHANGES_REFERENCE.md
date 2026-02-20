# Query Changes Reference - Multi-User Projects

## Quick Reference: What Changed?

### Core Principle
**Before:** `WHERE user_id = $1 AND project_id = $2`  
**After (for projects):** `WHERE project_id = $1` (shows ALL members' data)  
**After (for personal):** `WHERE user_id = $1 AND project_id IS NULL`

---

## 1. Project Queries (`utils/projects.py`)

### get_all_projects()
```sql
-- OLD: Only projects user owns
SELECT * FROM projects 
WHERE user_id = $1 AND is_active = TRUE

-- NEW: Projects user owns OR is a member of
SELECT DISTINCT p.*, 
       COALESCE(pm.role, 'owner') as role
FROM projects p
LEFT JOIN project_members pm ON p.project_id = pm.project_id AND pm.user_id = $1
WHERE p.is_active = TRUE
  AND (p.user_id = $1 OR pm.user_id = $1)
```

### get_project_by_id()
```sql
-- OLD: Only if user owns
SELECT * FROM projects 
WHERE user_id = $1 AND project_id = $2

-- NEW: If user owns OR is member
SELECT DISTINCT p.*,
       COALESCE(pm.role, 'owner') as role
FROM projects p
LEFT JOIN project_members pm ON p.project_id = pm.project_id AND pm.user_id = $1
WHERE p.project_id = $2
  AND (p.user_id = $1 OR pm.user_id = $1)
```

### get_project_stats()
```sql
-- OLD: Only user's expenses
SELECT COUNT(*), SUM(amount)
FROM expenses 
WHERE user_id = $1 AND project_id = $2

-- NEW: ALL members' expenses
SELECT COUNT(*), SUM(amount)
FROM expenses 
WHERE project_id = $1
```

---

## 2. Expense Queries (`utils/excel.py`)

### get_month_expenses()
```sql
-- OLD: Always filtered by user_id
SELECT e.amount, c.name 
FROM expenses e
JOIN categories c ON e.category_id = c.category_id
WHERE e.user_id = $1 AND e.month = $2
  AND ((e.project_id IS NULL AND $3 IS NULL) OR e.project_id = $3)

-- NEW: For projects - ALL members; For personal - only user
-- Projects:
SELECT e.amount, c.name 
FROM expenses e
JOIN categories c ON e.category_id = c.category_id
WHERE e.project_id = $1 AND e.month = $2

-- Personal:
SELECT e.amount, c.name 
FROM expenses e
JOIN categories c ON e.category_id = c.category_id
WHERE e.user_id = $1 AND e.month = $2 AND e.project_id IS NULL
```

### get_all_expenses()
```sql
-- OLD: Only user's expenses
SELECT e.*, c.name 
FROM expenses e
JOIN categories c ON e.category_id = c.category_id
WHERE e.user_id = $1 AND EXTRACT(YEAR FROM e.date) = $2
  AND ((e.project_id IS NULL AND $3 IS NULL) OR e.project_id = $3)

-- NEW: Includes user_id in results, shows all project members
-- Projects:
SELECT e.*, c.name, e.user_id  -- Shows WHO added each expense
FROM expenses e
JOIN categories c ON e.category_id = c.category_id
WHERE e.project_id = $1 AND EXTRACT(YEAR FROM e.date) = $2

-- Personal:
SELECT e.*, c.name, e.user_id
FROM expenses e
JOIN categories c ON e.category_id = c.category_id
WHERE e.user_id = $1 AND EXTRACT(YEAR FROM e.date) = $2
  AND e.project_id IS NULL
```

### get_category_expenses()
```sql
-- OLD: Only user's expenses in category
SELECT amount, month 
FROM expenses
WHERE user_id = $1 AND category_id = $2 
  AND EXTRACT(YEAR FROM date) = $3
  AND ((project_id IS NULL AND $4 IS NULL) OR project_id = $4)

-- NEW: For projects - ALL members; For personal - only user
-- Projects:
SELECT amount, month 
FROM expenses
WHERE category_id = $1 AND EXTRACT(YEAR FROM date) = $2
  AND project_id = $3

-- Personal:
SELECT amount, month 
FROM expenses
WHERE user_id = $1 AND category_id = $2 
  AND EXTRACT(YEAR FROM date) = $3
  AND project_id IS NULL
```

### Budget Update in add_expense()
```sql
-- OLD: Update user's budget based on user's expenses
UPDATE budget b
SET actual = (
    SELECT SUM(amount) FROM expenses e
    WHERE e.user_id = b.user_id 
      AND ((e.project_id IS NULL AND b.project_id IS NULL) 
           OR e.project_id = b.project_id)
      AND e.month = b.month
)
WHERE b.user_id = $1 AND b.month = $2
  AND ((b.project_id IS NULL AND $3 IS NULL) OR b.project_id = $3)

-- NEW: For projects - sum ALL members' expenses
-- Projects:
UPDATE budget b
SET actual = (
    SELECT SUM(amount) FROM expenses e
    WHERE e.project_id = b.project_id
      AND e.month = b.month
)
WHERE b.user_id = $1 AND b.project_id = $2 AND b.month = $3

-- Personal:
UPDATE budget b
SET actual = (
    SELECT SUM(amount) FROM expenses e
    WHERE e.user_id = b.user_id
      AND e.project_id IS NULL
      AND e.month = b.month
)
WHERE b.user_id = $1 AND b.project_id IS NULL AND b.month = $3
```

---

## 3. Category Queries (`utils/categories.py`)

### get_categories_for_user_project()
```sql
-- OLD: Only user's categories
SELECT * FROM categories
WHERE user_id = $1 AND is_active = TRUE
  AND (project_id = $2 OR project_id IS NULL)

-- NEW: For projects - ALL members' categories
-- Projects:
SELECT DISTINCT * FROM categories
WHERE is_active = TRUE
  AND (project_id = $1 OR project_id IS NULL)

-- Personal:
SELECT * FROM categories
WHERE user_id = $1 AND is_active = TRUE
  AND project_id IS NULL
```

### delete_category_with_transfer()
```sql
-- OLD: Transfer only user's expenses
UPDATE expenses
SET category_id = $1
WHERE category_id = $2 AND user_id = $3

-- NEW: For projects - transfer ALL members' expenses
-- Projects:
UPDATE expenses
SET category_id = $1
WHERE category_id = $2 AND project_id = $3

-- Personal:
UPDATE expenses
SET category_id = $1
WHERE category_id = $2 AND user_id = $3 AND project_id IS NULL
```

---

## 4. New Helper Functions (`utils/projects.py`)

### is_project_member()
```sql
-- Check if user has access to project
SELECT 1
FROM projects p
LEFT JOIN project_members pm ON p.project_id = pm.project_id AND pm.user_id = $1
WHERE p.project_id = $2 AND p.is_active = TRUE
  AND (p.user_id = $1 OR pm.user_id = $1)
```

### get_user_role_in_project()
```sql
-- Get user's role (owner, editor, viewer, or NULL)
SELECT COALESCE(
    pm.role,
    CASE WHEN p.user_id = $1 THEN 'owner' ELSE NULL END
) as role
FROM projects p
LEFT JOIN project_members pm ON p.project_id = pm.project_id AND pm.user_id = $1
WHERE p.project_id = $2 AND p.is_active = TRUE
```

### get_project_members()
```sql
-- Get all members including owner
SELECT p.user_id, 'owner' as role, NULL as joined_at
FROM projects p
WHERE p.project_id = $1 AND p.is_active = TRUE
UNION
SELECT pm.user_id, pm.role, pm.joined_at
FROM project_members pm
WHERE pm.project_id = $1
```

---

## 5. Access Validation Pattern

All functions that work with project data now follow this pattern:

```python
async def get_data_for_project(user_id, project_id=None):
    """Get data for user or project"""
    
    # 1. Validate access if project_id is specified
    if project_id is not None:
        from utils import projects
        if not await projects.is_project_member(user_id, project_id):
            # Return empty result or raise error
            return {'total': 0, 'data': []}
    
    # 2. Query based on context
    if project_id is not None:
        # For projects: get ALL members' data
        rows = await db.fetch(
            "SELECT * FROM expenses WHERE project_id = $1",
            project_id
        )
    else:
        # For personal: get only user's data
        rows = await db.fetch(
            "SELECT * FROM expenses WHERE user_id = $1 AND project_id IS NULL",
            str(user_id)
        )
    
    # 3. Return results
    return process_results(rows)
```

---

## 6. Key Decision Points in Code

When writing new queries, ask:

### Question 1: Is this for a project or personal data?
```python
if project_id is not None:
    # Project query - show ALL members' data
else:
    # Personal query - show only user's data
```

### Question 2: Does this need access control?
```python
if project_id is not None:
    if not await projects.is_project_member(user_id, project_id):
        return []  # Access denied
```

### Question 3: Should I filter by user_id?
```python
# Projects: NO - show all members
if project_id is not None:
    WHERE project_id = $1

# Personal: YES - show only user
else:
    WHERE user_id = $1 AND project_id IS NULL
```

---

## 7. Migration Checklist

For any existing query:

1. ✅ Does it use `WHERE user_id = $1`?
   - If yes, consider whether it should show all members' data for projects

2. ✅ Does it use `WHERE project_id = $2`?
   - If yes, make sure it validates user has access first

3. ✅ Does it handle both project and personal data?
   - If yes, split into two code paths (one for project, one for personal)

4. ✅ Does it need to know WHO did something?
   - If yes, include `user_id` in SELECT or return values

5. ✅ Does it modify data?
   - If yes, consider whether modifications should affect all members or just user

---

## 8. Common Patterns

### Pattern: Conditional Query Based on Project
```python
if project_id is not None:
    query = "SELECT * FROM expenses WHERE project_id = $1"
    params = [project_id]
else:
    query = "SELECT * FROM expenses WHERE user_id = $1 AND project_id IS NULL"
    params = [str(user_id)]

rows = await db.fetch(query, *params)
```

### Pattern: Access Validation
```python
from utils import projects

if project_id is not None:
    if not await projects.is_project_member(user_id, project_id):
        raise PermissionError("Access denied to project")
```

### Pattern: Including User Attribution
```python
# In SELECT queries for projects, include user_id to show who did what
SELECT 
    e.*,
    e.user_id,  -- Shows who added this expense
    c.name
FROM expenses e
WHERE e.project_id = $1
```

---

## Quick Migration Tool

Use this regex to find queries that might need updating:

```regex
# Find queries filtering by user_id and project_id together
WHERE.*user_id.*AND.*project_id

# Find queries filtering only by user_id (might need project split)
WHERE\s+(\w+\.)?user_id\s*=\s*\$\d+

# Find queries with old project_id pattern
AND\s+\(\(.*project_id\s+IS\s+NULL.*OR.*project_id\s*=
```
