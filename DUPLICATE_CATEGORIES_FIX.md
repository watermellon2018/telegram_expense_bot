# Duplicate Categories Fix

## What Was Wrong

Categories were showing up twice in project category lists:

```
📋 Список категорий
📁 Проект: тест

🔵 Системные категории:
🏡 дом        ← Duplicate
🏡 дом        ← Duplicate
🐶 животные   ← Duplicate
🐶 животные   ← Duplicate
```

---

## Why It Happened

When showing categories for a project, the query was returning BOTH:
1. **Global categories** (project_id IS NULL) - System categories
2. **Project-specific categories** (project_id = 4) - Same names

This happens when:
- System categories are copied to a project
- A user creates a category with the same name as a global one
- Categories exist in multiple scopes

---

## The Fix

### Changed File: `utils/categories.py`

**Before:**
```sql
SELECT DISTINCT c.category_id, c.name, c.is_system, ...
FROM categories c
WHERE c.is_active = TRUE
  AND (c.project_id = $1 OR c.project_id IS NULL)
ORDER BY c.is_system DESC, c.name ASC
```

This returned all matching categories, including duplicates by name.

**After:**
```sql
WITH deduplicated AS (
    SELECT DISTINCT ON (LOWER(c.name)) 
           c.category_id, c.name, c.is_system, ...
    FROM categories c
    WHERE c.is_active = TRUE
      AND (c.project_id = $1 OR c.project_id IS NULL)
    ORDER BY LOWER(c.name), 
             CASE WHEN c.project_id = $1 THEN 0 ELSE 1 END,
             c.is_system DESC
)
SELECT * FROM deduplicated
ORDER BY is_system DESC, name ASC
```

**How it works:**
1. `DISTINCT ON (LOWER(c.name))` - Keep only ONE category per unique name (case-insensitive)
2. Priority order when duplicates exist:
   - Prefers **project-specific** categories (`project_id = $1`)
   - Then **global** categories (`project_id IS NULL`)
   - Then **system** categories over user categories
3. Final result ordered by: system categories first, then alphabetically

---

## What Happens Now

### Scenario 1: Both Global and Project Category Exist

Database has:
- Category: "дом" (project_id: NULL, is_system: true) ← Global
- Category: "дом" (project_id: 4, is_system: true) ← Project-specific

**Result:** Shows only the **project-specific** "дом"

### Scenario 2: Only Global Category Exists

Database has:
- Category: "дом" (project_id: NULL, is_system: true)

**Result:** Shows the **global** "дом"

### Scenario 3: User Created Category

Database has:
- Category: "дом" (project_id: NULL, is_system: true) ← System
- Category: "дом" (project_id: 4, is_system: false, user_id: 123) ← User created

**Result:** Shows the **user-created** project-specific "дом" (because project-specific is preferred)

---

## Testing

**Restart bot and check:**

```bash
python main.py
```

**In Telegram:**
1. Go to categories menu
2. Check category list
3. Should see each category only ONCE

**Example - Before:**
```
🏡 дом
🏡 дом
🐶 животные
🐶 животные
```

**Example - After:**
```
🏡 дом
🐶 животные
```

---

## Optional: Database Cleanup

You can optionally clean up duplicate categories in the database using:

```bash
psql -U bot_user -d botdb -f migration/fix_duplicate_categories.sql
```

This will:
1. Show you all duplicate categories
2. Optionally deactivate global duplicates (if you uncomment the code)

**Note:** You don't NEED to clean the database. The query now handles duplicates automatically by showing only one version.

---

## Root Cause

Categories can have the same name in different scopes due to the unique constraint:

```sql
CREATE UNIQUE INDEX categories_project_name_idx
    ON categories (project_id, LOWER(name))
    WHERE is_active = true;
```

This allows:
- "дом" with project_id = NULL ✅
- "дом" with project_id = 4 ✅
- "дом" with project_id = 5 ✅

But NOT:
- Two "дом" with project_id = 4 ❌

---

## Prevention

To prevent future duplicates when creating categories, the code should:
1. Check if category exists globally before creating project-specific
2. Or use the global category instead of creating a duplicate
3. Or clearly distinguish project categories from global ones

Current behavior:
- Users can create project-specific categories with same names as globals
- The query now prioritizes showing project-specific over global
- No user-facing duplicate display

---

## Summary

**Problem:** Duplicate category names showing in project lists  
**Cause:** Same category name in both global and project scope  
**Fix:** Use `DISTINCT ON (name)` with priority for project-specific  
**Impact:** Category lists now show unique names only  
**Database:** No cleanup required (but optional script provided)  
**Testing:** Restart bot and check category list  

**Status:** ✅ FIXED - No more duplicates in category lists!
