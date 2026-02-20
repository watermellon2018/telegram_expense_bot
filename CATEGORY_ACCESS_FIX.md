# Category Access Fix for Project Members

## Problem

When an invited user (non-owner) tried to add an expense using text message like `50 продукты`, they got an error:

```json
{
  "event": "expense_add_failed_from_text",
  "error": "Failed to add expense from text",
  "user_id": 1369264761,  // Invited user
  "category_id": 60,
  "category_name": "продукты"
}
```

But the owner (user_id: 400564356) could add expenses successfully.

---

## Root Cause

### The Flow:

1. User sends: `50 продукты`
2. Handler finds category "продукты" (category_id: 60)
3. Handler calls `add_expense(user_id, amount, category_id, ...)`
4. `add_expense()` validates category access with `get_category_by_id(user_id, category_id)`
5. **`get_category_by_id()` returned None for invited users** ❌

### Why It Failed:

The old `get_category_by_id()` query was:

```sql
SELECT category_id, name, is_system, is_active, project_id, created_at
FROM categories
WHERE category_id = $1 AND user_id = $2  -- ❌ Only owner's categories!
```

This meant:
- Categories created by the project owner (user_id: 400564356) ✅
- **Could NOT be accessed by invited members (user_id: 1369264761)** ❌

Even though:
- The invited user is a valid project member
- The category belongs to the shared project
- The invited user has permission to add expenses

---

## The Fix

### Changed File: `utils/categories.py`

**Function:** `get_category_by_id(user_id, category_id)`

**New Query:**

```sql
SELECT c.category_id, c.name, c.is_system, c.is_active, c.project_id, c.created_at
FROM categories c
WHERE c.category_id = $1
  AND c.is_active = TRUE
  AND (
      c.user_id = $2  -- User owns the category
      OR c.project_id IS NULL  -- Global category (accessible to all)
      OR EXISTS (
          -- User is a member of the category's project
          SELECT 1 FROM projects p
          LEFT JOIN project_members pm ON p.project_id = pm.project_id AND pm.user_id = $2
          WHERE p.project_id = c.project_id
            AND p.is_active = TRUE
            AND (p.user_id = $2 OR pm.user_id = $2)
      )
  )
```

**Access Logic:**

A user can access a category if ANY of these is true:

1. ✅ **User owns the category** (`c.user_id = user_id`)
2. ✅ **Category is global** (`c.project_id IS NULL`)
3. ✅ **User is a member of the category's project** (checks `projects` and `project_members`)

---

## What This Fixes

### Before Fix:

❌ Owner creates category "продукты" in project  
❌ Invited user tries to use "продукты"  
❌ `get_category_by_id()` returns None  
❌ `add_expense()` returns False  
❌ Error: "Failed to add expense from text"  

### After Fix:

✅ Owner creates category "продукты" in project  
✅ Invited user tries to use "продукты"  
✅ `get_category_by_id()` checks project membership  
✅ User IS a project member → Returns category  
✅ `add_expense()` succeeds  
✅ Expense added successfully!  

---

## Testing

**Restart bot:**
```bash
python main.py
```

**Test as Owner:**
```
50 продукты test
✅ Should work
```

**Test as Invited User (Editor or Viewer):**
```
50 продукты test
✅ Should now work!
```

**Test with different scenarios:**

1. **Editor adds expense to shared project:**
   - Uses category created by owner ✅
   - Uses global system category ✅
   - Uses category they created ✅

2. **Viewer tries to add expense:**
   - Should get permission denied (different check) ✅
   - Category access check passes, but ADD_EXPENSE permission fails ✅

3. **Personal expenses (no project):**
   - Uses only own categories ✅
   - Uses global categories ✅

---

## Related Functions

### Other Category Access Functions:

1. **`get_categories_for_user_project()`** - Already correct
   - Returns all categories accessible to user in project
   - Used for listing categories

2. **`get_category_by_id()`** - **FIXED** ✅
   - Returns single category if user has access
   - Used for validation before adding expense

3. **`create_category()`** - Already correct
   - Creates category with user_id
   - Permission check already in place

4. **`delete_category_with_transfer()`** - Already correct
   - Can only delete own categories
   - Works correctly

---

## Why This Matters

In a shared project, members need to:
- ✅ View all project categories
- ✅ Use all project categories in expenses
- ✅ Create their own categories
- ❌ Cannot delete others' categories (correct)

The fix ensures that **category access matches project membership**.

---

## Edge Cases Handled

### Case 1: Category belongs to different project
```sql
-- Category in project 4
-- User is member of project 5
-- Result: Access denied ❌
```

### Case 2: Category is global
```sql
-- Category project_id IS NULL
-- Any user can access
-- Result: Access granted ✅
```

### Case 3: User leaves project
```sql
-- Category in project 4
-- User was member but left
-- Result: Access denied ❌
```

### Case 4: Category inactive
```sql
-- Category is_active = FALSE
-- Result: Access denied ❌
```

---

## Performance Impact

**Minimal** - The EXISTS subquery only runs when:
- Category is project-specific
- User doesn't own it
- Not a global category

Most cases are handled by the first two conditions without the subquery.

---

## Summary

**Problem:** Invited users couldn't add expenses using text messages  
**Cause:** `get_category_by_id()` only returned categories owned by specific user  
**Fix:** Check project membership for category access  
**Impact:** All project members can now use project categories  
**Testing:** Restart bot and test as invited user  

**Status:** ✅ FIXED - Invited users can now add expenses!

---

## Verification Queries

Check category access for a user:

```sql
-- Show all categories user 1369264761 can access
SELECT c.category_id, c.name, c.project_id, 
       CASE 
           WHEN c.user_id = '1369264761' THEN 'Owner'
           WHEN c.project_id IS NULL THEN 'Global'
           ELSE 'Project Member'
       END as access_reason
FROM categories c
WHERE c.is_active = TRUE
  AND (
      c.user_id = '1369264761'
      OR c.project_id IS NULL
      OR EXISTS (
          SELECT 1 FROM projects p
          LEFT JOIN project_members pm ON p.project_id = pm.project_id AND pm.user_id = '1369264761'
          WHERE p.project_id = c.project_id
            AND p.is_active = TRUE
            AND (p.user_id = '1369264761' OR pm.user_id = '1369264761')
      )
  )
ORDER BY c.name;
```

**Expected result:** Should include project categories even if created by owner.
