# Permission System - Quick Reference

## For Developers: Adding Permission Checks

### Step 1: Import Permission Module
```python
from utils.permissions import Permission, has_permission
```

### Step 2: Check Permission Before Operation
```python
async def my_function(user_id, project_id):
    # Check if user has permission
    if not await has_permission(user_id, project_id, Permission.ADD_EXPENSE):
        return {'success': False, 'message': 'Нет прав на операцию'}
    
    # Proceed with operation
    # ...
```

### Step 3: Personal vs Project Logic
```python
async def my_function(user_id, project_id=None):
    # Personal operations (project_id=None) - no permission check needed
    if project_id is None:
        # User can always modify their own personal data
        pass
    else:
        # Project operations - check permission
        if not await has_permission(user_id, project_id, Permission.ADD_EXPENSE):
            return {'success': False, 'message': 'Нет прав'}
```

---

## Quick Permission Reference

### Database Modifications

| Operation | Permission | Allowed Roles |
|-----------|-----------|---------------|
| Add expense | `Permission.ADD_EXPENSE` | Owner, Editor |
| Edit expense | `Permission.EDIT_EXPENSE` | Owner, Editor |
| Delete expense | `Permission.DELETE_EXPENSE` | Owner, Editor |
| Add category | `Permission.ADD_CATEGORY` | Owner, Editor |
| Edit category | `Permission.EDIT_CATEGORY` | Owner, Editor |
| Delete category | `Permission.DELETE_CATEGORY` | Owner, Editor |
| Set budget | `Permission.SET_BUDGET` | Owner, Editor |

### View Operations

| Operation | Permission | Allowed Roles |
|-----------|-----------|---------------|
| View stats | `Permission.VIEW_STATS` | Owner, Editor, Viewer |
| View history | `Permission.VIEW_HISTORY` | Owner, Editor, Viewer |
| View members | `Permission.VIEW_MEMBERS` | Owner, Editor, Viewer |
| View budget | `Permission.VIEW_BUDGET` | Owner, Editor, Viewer |

### Project Management

| Operation | Permission | Allowed Roles |
|-----------|-----------|---------------|
| Delete project | `Permission.DELETE_PROJECT` | Owner only |
| Invite members | `Permission.INVITE_MEMBERS` | Owner only |
| Remove members | `Permission.REMOVE_MEMBERS` | Owner only |
| Change roles | `Permission.CHANGE_ROLES` | Owner only |

---

## Common Patterns

### Pattern 1: Simple Permission Check
```python
from utils.permissions import Permission, has_permission

if not await has_permission(user_id, project_id, Permission.ADD_EXPENSE):
    return {'success': False, 'message': 'Permission denied'}
```

### Pattern 2: Require Permission (raises exception)
```python
from utils.permissions import Permission, require_permission

try:
    await require_permission(user_id, project_id, Permission.DELETE_PROJECT)
    # Proceed with operation
except PermissionError as e:
    return {'success': False, 'message': str(e)}
```

### Pattern 3: Get All User Permissions
```python
from utils.permissions import get_user_permissions

permissions = await get_user_permissions(user_id, project_id)
if Permission.ADD_EXPENSE in permissions:
    # User can add expenses
    pass
```

### Pattern 4: Check Own Resource
```python
from utils.permissions import can_modify_expense

# Users can always modify their own expenses
# Editors/Owners can modify any expense in project
if await can_modify_expense(user_id, expense_user_id, project_id):
    # Can modify
    pass
```

---

## Invitation System Quick Guide

### Create Invitation (Owner Only)
```python
from utils import projects

result = await projects.create_invitation(
    user_id=owner_id,
    project_id=project_id,
    role='editor',  # or 'viewer'
    expires_in_hours=24
)

if result['success']:
    token = result['token']
    link = await projects.get_invitation_link(token, bot_username)
    # Share link with invitee
```

### Accept Invitation (Any User)
```python
result = await projects.accept_invitation(user_id, token)
# Automatically handled in /start inv_TOKEN
```

### Remove Member (Owner Only)
```python
result = await projects.remove_member(owner_id, project_id, member_id)
```

### Change Role (Owner Only)
```python
result = await projects.change_member_role(
    owner_id, project_id, member_id, new_role='viewer'
)
```

---

## Error Messages

### Russian (for users)
```python
"❌ У вас нет прав на добавление расходов в этом проекте"
"❌ Только владелец может удалить проект"
"❌ Только владелец может приглашать участников"
"❌ Проект не найден или у вас нет доступа"
```

### English (for logs)
```python
"Permission denied: user {user_id} does not have {permission}"
"Access denied: user {user_id} not a member of project {project_id}"
"Operation restricted to owner only"
```

---

## Testing Permissions

### Test Permission Check
```python
from utils.permissions import Permission, has_permission

# Test as owner
assert await has_permission(owner_id, project_id, Permission.DELETE_PROJECT)

# Test as editor
assert await has_permission(editor_id, project_id, Permission.ADD_EXPENSE)
assert not await has_permission(editor_id, project_id, Permission.DELETE_PROJECT)

# Test as viewer
assert await has_permission(viewer_id, project_id, Permission.VIEW_STATS)
assert not await has_permission(viewer_id, project_id, Permission.ADD_EXPENSE)

# Test non-member
assert not await has_permission(outsider_id, project_id, Permission.VIEW_STATS)
```

---

## Role Descriptions (for UI)

### Get Role Description
```python
from utils.permissions import get_role_description

get_role_description('owner')   # "👑 Владелец"
get_role_description('editor')  # "✏️ Редактор"
get_role_description('viewer')  # "👁️ Наблюдатель"
```

### Get Role Permissions List
```python
from utils.permissions import get_role_permissions_list

permissions = get_role_permissions_list('editor')
# Returns list of human-readable permission names
```

---

## When to Check Permissions

✅ **Always check for:**
- Database modifications (INSERT, UPDATE, DELETE)
- Project management operations
- Member management operations

❌ **No need to check for:**
- Personal data operations (project_id=None)
- Public data (e.g., system categories)
- Non-sensitive reads

---

## Logging

Permission checks are automatically logged:

```python
# Success
log_event(logger, "permission_granted", 
          user_id=user_id, project_id=project_id,
          role=role, permission=permission.value)

# Denied
log_event(logger, "permission_denied_insufficient_role",
          user_id=user_id, project_id=project_id,
          role=role, permission=permission.value)

# Not a member
log_event(logger, "permission_denied_not_member",
          user_id=user_id, project_id=project_id,
          permission=permission.value)
```

---

## Complete Example

```python
from utils.permissions import Permission, has_permission
from utils import excel, projects

async def handle_add_expense(user_id, project_id, amount, category_id, description):
    """
    Add expense with permission check
    """
    # 1. Check permission (for projects)
    if project_id is not None:
        if not await has_permission(user_id, project_id, Permission.ADD_EXPENSE):
            return {
                'success': False,
                'message': 'У вас нет прав на добавление расходов в этом проекте'
            }
    
    # 2. Perform operation (permission check also inside excel.add_expense)
    success = await excel.add_expense(
        user_id=user_id,
        amount=amount,
        category_id=category_id,
        description=description,
        project_id=project_id
    )
    
    # 3. Return result
    if success:
        return {'success': True, 'message': 'Расход добавлен'}
    else:
        return {'success': False, 'message': 'Ошибка при добавлении расхода'}
```

---

## Migration Checklist

When adding permission checks to existing code:

- [ ] Import `Permission` and `has_permission`
- [ ] Add permission check before database operation
- [ ] Handle permission denied gracefully
- [ ] Return appropriate error message
- [ ] Add logging for denied permissions
- [ ] Test with all three roles
- [ ] Test with non-members
- [ ] Verify personal operations still work

---

## Common Mistakes to Avoid

❌ **Don't:**
- Check permissions after modifying database
- Use hardcoded role strings ('owner' vs Permission enum)
- Forget to check permissions in project operations
- Return error exceptions to users (catch and return message)

✅ **Do:**
- Check permissions before database operations
- Use Permission enum constants
- Log permission denials
- Return user-friendly error messages
- Test all roles thoroughly
