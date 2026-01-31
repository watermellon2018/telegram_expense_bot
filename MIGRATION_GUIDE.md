# Migration Guide: Text Categories to Normalized Categories

This guide explains how to migrate from the old text-based category system to the new normalized category system with user-defined and project-scoped categories.

## Overview

The migration introduces:
- A new `categories` table with user-defined and project-scoped categories
- `expenses.category_id` (FK) replacing `expenses.category` (text)
- Full backward compatibility during migration
- Support for creating custom categories per project

## Database Migration

### Step 1: Run the Migration SQL

Execute the migration script:

```bash
psql -U bot_user -d botdb -f migrate_to_categories.sql
```

Or using Python:

```python
import asyncio
import asyncpg
from pathlib import Path

async def run_migration():
    # Load your DB connection settings
    conn = await asyncpg.connect("postgresql://user:pass@host:port/dbname")
    
    # Read and execute migration
    with open("migrate_to_categories.sql", "r") as f:
        await conn.execute(f.read())
    
    await conn.close()

asyncio.run(run_migration())
```

### What the Migration Does

1. **Creates `categories` table** with:
   - `category_id` (PK, SERIAL)
   - `user_id` (FK → users)
   - `project_id` (FK → projects, nullable for global categories)
   - `name` (VARCHAR)
   - `is_system` (BOOLEAN) - marks default categories
   - `is_active` (BOOLEAN) - for soft deletes
   - `created_at` (TIMESTAMP)
   - Unique constraint on (user_id, project_id, LOWER(name))

2. **Adds `category_id` column** to `expenses` table (nullable initially)

3. **Migrates existing data**:
   - Creates system categories for all users from `config.DEFAULT_CATEGORIES`
   - Links existing expenses to categories by matching category names
   - Creates non-system categories for any unmatched category names

4. **Makes `category_id` NOT NULL** after migration completes

5. **Keeps old `category` column** for backward compatibility (can be dropped later)

## Code Changes

### New Module: `utils/categories.py`

Provides functions for category management:
- `get_categories_for_user_project()` - Get categories for user/project
- `create_category()` - Create new category
- `deactivate_category()` - Soft delete category
- `get_category_by_id()` - Get category by ID
- `ensure_system_categories_exist()` - Initialize system categories for user

### Updated Functions

**`utils/excel.py`:**
- `add_expense()` now accepts `category_id` (int) instead of `category` (str)
- Still supports string category names for backward compatibility (looks up by name)
- All query functions updated to JOIN with categories table

**`handlers/expense.py`:**
- Category selection now uses inline keyboards with callback queries
- Added "➕ Create category" button in category menu
- New conversation state `CREATING_CATEGORY` for category creation flow
- Text parsing handlers updated to look up categories by name

**`handlers/stats.py`:**
- Category commands updated to work with new category system
- Category lookup by name with fallback to global categories

## Backward Compatibility

The system maintains backward compatibility:

1. **Text commands** (`/add 100 продукты`) still work - the system looks up category by name
2. **Old `category` column** is kept in expenses table (can be dropped later)
3. **Legacy category names** are automatically migrated to system categories

## Testing the Migration

### Before Migration

1. Note current expense count:
   ```sql
   SELECT COUNT(*) FROM expenses;
   ```

2. Note unique category names:
   ```sql
   SELECT DISTINCT category FROM expenses;
   ```

### After Migration

1. Verify all expenses have category_id:
   ```sql
   SELECT COUNT(*) FROM expenses WHERE category_id IS NULL;
   -- Should return 0
   ```

2. Verify categories were created:
   ```sql
   SELECT COUNT(*) FROM categories;
   -- Should have at least system categories for each user
   ```

3. Test expense creation via bot:
   - Use `/add` command
   - Verify inline keyboard shows categories
   - Test creating a new category
   - Verify expense is created successfully

## Rollback Plan

If you need to rollback:

1. **Keep old category column** - it's preserved by default
2. **Revert code changes** - restore previous version
3. **Drop new column** (if needed):
   ```sql
   ALTER TABLE expenses DROP COLUMN IF EXISTS category_id;
   DROP TABLE IF EXISTS categories;
   ```

## Post-Migration Cleanup

After verifying everything works:

1. **Drop old category column** (optional):
   ```sql
   ALTER TABLE expenses DROP COLUMN IF EXISTS category;
   ```

2. **Monitor category usage**:
   ```sql
   -- Categories not used in expenses
   SELECT c.* FROM categories c
   LEFT JOIN expenses e ON c.category_id = e.category_id
   WHERE e.category_id IS NULL AND c.is_active = TRUE;
   ```

## Key Features

### User-Defined Categories
- Users can create custom categories scoped to their active project
- Categories are project-specific or global (project_id = NULL)
- Duplicate names prevented within same scope

### System Categories
- Default categories from `config.DEFAULT_CATEGORIES` are marked as system
- System categories are created automatically for each user
- System categories appear first in category selection menu

### Soft Deletes
- Categories use `is_active` flag instead of hard deletes
- Categories used in expenses cannot be deactivated
- Historical expenses remain consistent after category renaming

## Troubleshooting

### Migration fails with "category_id IS NULL"
- Check that all category names in expenses match categories in categories table
- The migration creates missing categories automatically, but verify manually

### Categories not showing in menu
- Ensure `ensure_system_categories_exist()` is called for the user
- Check that categories have `is_active = TRUE`
- Verify project_id matches active project

### Expense creation fails
- Check that category_id exists and belongs to user
- Verify category is active and available for project scope
- Check logs for specific error messages
