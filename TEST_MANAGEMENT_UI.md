# Testing Project Management UI - Quick Start

## Prerequisites

1. Bot running with latest code
2. Database migrated (multi-user support)
3. At least 2 test Telegram accounts

---

## Test Scenario 1: Owner Creates and Manages Project

### Setup (Owner - User A):

```bash
# 1. Create a test project
/project_create Test Team

# 2. Access project settings
# Click "📁 Проекты" button
# Click "⚙️ Управление" button
# You should see:
# - ✉️ Пригласить участника
# - 👥 Участники проекта
# - ⚙️ Управление ролями
```

**Expected:**
- Settings menu shows with owner options
- No "🚪 Покинуть проект" button (owner can't leave)
- Project info displays correctly

---

## Test Scenario 2: Generate and Use Invitation

### Owner (User A):

```bash
# 1. Click "✉️ Пригласить участника"
# 2. Click "✏️ Редактор"
# 3. Copy invitation link
```

**Expected:**
```
✅ Приглашение создано!

📁 Test Team
✏️ Редактор

Отправьте эту ссылку участнику:
`https://t.me/your_bot?start=inv_abc123...`

⏰ Действительна до: 2026-02-02 12:00
```

### New Member (User B):

```bash
# 1. Click invitation link
# 2. Bot automatically adds to project
```

**Expected:**
```
✅ Вы добавлены в проект 'Test Team' с ролью 'editor'

📁 Test Team
✏️ Редактор

Теперь вы можете добавлять расходы...
```

---

## Test Scenario 3: View Members List

### Owner (User A):

```bash
# 1. In project settings, click "👥 Участники проекта"
```

**Expected:**
```
📁 Test Team

👥 Участники (2):

👑 Владелец
ID: 12345 (владелец)
Присоединился: 2026-01-15

✏️ Редактор
ID: 67890
Присоединился: 2026-02-01
[👤 67890...] [🔄 Роль] [❌ Удалить]

[« Назад]
```

### Editor (User B):

```bash
# 1. Click "⚙️ Управление"
# 2. Click "👥 Участники проекта"
```

**Expected:**
- Same member list
- NO management buttons (read-only view)
- Can see all members and their roles

---

## Test Scenario 4: Change Member Role

### Owner (User A):

```bash
# 1. Click "⚙️ Управление ролями"
# 2. Click "↔️ Изменить на 👁️" for User B
```

**Expected:**
- Popup: "✅ Роль изменена"
- View refreshes automatically
- User B now shows as Viewer

### Verify as User B:

```bash
# 1. Try to add expense: /add 100 продукты
```

**Expected:**
```
❌ У вас нет прав на добавление расходов в этом проекте
```

---

## Test Scenario 5: Change Role Back

### Owner (User A):

```bash
# 1. Click "⚙️ Управление ролями"
# 2. Click "↔️ Изменить на ✏️" for User B
```

**Expected:**
- Popup: "✅ Роль изменена"
- User B back to Editor
- Can add expenses again

---

## Test Scenario 6: Remove Member

### Owner (User A):

```bash
# 1. Click "👥 Участники проекта"
# 2. Click "❌ Удалить" next to User B
# 3. Confirm removal
```

**Expected:**
```
⚠️ Вы уверены, что хотите удалить участника?

ID: 67890

Участник потеряет доступ к проекту.

[✅ Да, удалить] [❌ Отмена]
```

After confirmation:
- Popup: "✅ Участник удален"
- Member list updates
- User B no longer in list

### Verify as User B:

```bash
# 1. Try to view project stats: /month
```

**Expected:**
- Empty results (no access)
- Project not in project list

---

## Test Scenario 7: Re-invite and Test Leave

### Owner (User A):

```bash
# 1. Create new invitation as Viewer
# 2. Share with User B
```

### New Member (User B):

```bash
# 1. Click invitation link
# 2. Added as Viewer
# 3. Go to project settings: Click "⚙️ Управление"
# 4. Click "🚪 Покинуть проект"
# 5. Confirm leaving
```

**Expected:**
```
⚠️ Вы уверены, что хотите покинуть проект?

📁 Test Team

Вы потеряете доступ к данным проекта.

[✅ Да, покинуть] [❌ Отмена]
```

After confirmation:
```
✅ Вы покинули проект 'Test Team'

Вы больше не являетесь участником проекта.
```

---

## Test Scenario 8: Owner Cannot Leave

### Owner (User A):

```bash
# 1. Click "⚙️ Управление"
# 2. Verify NO "🚪 Покинуть проект" button
```

**Expected:**
- Leave button NOT shown for owner
- Only shows invite, members, role management options

---

## Test Scenario 9: Multi-Member Role Management

### Setup:
- User A (Owner)
- User B (Editor)
- User C (Viewer)

### Owner (User A):

```bash
# 1. Click "⚙️ Управление ролями"
```

**Expected:**
```
⚙️ Управление ролями

📁 Test Team

✏️ Редактор ID: 67890
[↔️ Изменить на 👁️]

👁️ Наблюдатель ID: 11111
[↔️ Изменить на ✏️]

[« Назад]
```

Test toggling roles for multiple members.

---

## Test Scenario 10: Permission Enforcement

### Viewer (User C):

```bash
# Try each restricted action:
# 1. /invite editor
# Expected: ❌ Только владелец может приглашать участников

# 2. Try to kick someone (no button visible)
# Expected: No kick buttons in members list

# 3. /add 100 продукты
# Expected: ❌ У вас нет прав на добавление расходов
```

### Editor (User B):

```bash
# Try owner-only actions:
# 1. /invite viewer
# Expected: ❌ Только владелец может приглашать участников

# 2. Try to see role management (no button visible)
# Expected: No "⚙️ Управление ролями" option in settings

# Allowed actions:
# 3. /add 100 продукты
# Expected: ✅ Расход добавлен

# 4. View members
# Expected: ✅ Can see members list (read-only)
```

---

## Error Cases to Test

### 1. No Active Project:

```bash
# Without selecting a project:
/project_settings
```

**Expected:**
```
❌ Нет активного проекта.
Сначала выберите проект командой /projects или создайте новый.
```

### 2. Invalid Project Access:

```bash
# User not in project tries to access it
# (manually construct callback, or use old project_id)
```

**Expected:**
```
❌ Проект не найден или у вас нет доступа
```

### 3. Expired Invitation:

```bash
# Wait 24+ hours or manually expire in DB
# Then try to use invitation link
```

**Expected:**
```
❌ Приглашение истекло
```

### 4. Already a Member:

```bash
# Try to accept invitation for project you're already in
```

**Expected:**
```
❌ Вы уже участник проекта 'Test Team' с ролью 'editor'
```

---

## Navigation Flow Tests

### Test 1: Complete Navigation

```
Main Menu
  → 📁 Проекты
    → ⚙️ Управление
      → 👥 Участники проекта
        → [« Назад]
      → ⚙️ Управление ролями
        → Change role
        → [« Назад]
      → ✉️ Пригласить участника
        → Select role
        → See link
        → [« Назад к настройкам]
```

All navigation should work smoothly without dead ends.

### Test 2: Back Button Chain

```
Click: ⚙️ Управление
  → 👥 Участники
    → [« Назад] → Returns to settings
  → ✉️ Пригласить
    → Select role
    → [« Назад к настройкам] → Returns to settings
```

---

## Performance Tests

### Load Test:

```bash
# With 10+ members in project:
# 1. View members list
# 2. Open role management
# 3. All operations should be instant (<1s)
```

### Concurrent Operations:

```bash
# User A and User B both:
# 1. View members list simultaneously
# 2. A changes B's role while B views list
# 3. Both should see consistent state
```

---

## UI/UX Validation

### Check These Elements:

- [ ] All buttons visible and clickable
- [ ] Text formatting correct (no weird characters)
- [ ] Emojis display properly
- [ ] Role descriptions show correctly
- [ ] Confirmations appear for destructive actions
- [ ] Success/error messages clear and helpful
- [ ] Navigation intuitive (can get anywhere in 3 clicks)
- [ ] Mobile-friendly (buttons not too small)

---

## Regression Tests

Ensure existing functionality still works:

- [ ] `/project_create` still works
- [ ] `/project_list` shows all projects
- [ ] `/project_select` switches projects
- [ ] `/project_delete` deletes (owner only)
- [ ] `/invite` command works alongside UI
- [ ] `/members` command works alongside UI
- [ ] Expenses still added to correct project
- [ ] Stats show combined member data
- [ ] Personal expenses unaffected

---

## Logging Verification

Check logs for these events:

```bash
# When testing, these should appear:
project_settings_opened
members_list_viewed
invitation_created_via_ui
role_changed_via_ui
member_kicked_via_ui
user_left_via_ui
```

All actions should be logged with:
- user_id
- project_id
- timestamp
- relevant details (role, member_id, etc.)

---

## Checklist Summary

- [ ] Owner can access all management features
- [ ] Editor can view but not manage
- [ ] Viewer can view but not modify
- [ ] Invitations work with both roles
- [ ] Role changes apply immediately
- [ ] Member removal works correctly
- [ ] Leave project works for non-owners
- [ ] Owner cannot leave
- [ ] All permissions enforced
- [ ] Navigation works smoothly
- [ ] Confirmations shown for critical actions
- [ ] Success/error messages appropriate
- [ ] Logging captures all events
- [ ] No broken functionality
- [ ] Mobile UI acceptable

---

## Quick Test Script

For automated/semi-automated testing:

```python
async def quick_test():
    # Setup
    owner_id = 12345
    editor_id = 67890
    
    # Create project
    result = await projects.create_project(owner_id, "Test Project")
    project_id = result['project_id']
    
    # Create invitation
    result = await projects.create_invitation(owner_id, project_id, 'editor')
    token = result['token']
    
    # Accept invitation
    result = await projects.accept_invitation(editor_id, token)
    assert result['success']
    
    # Change role
    result = await projects.change_member_role(owner_id, project_id, editor_id, 'viewer')
    assert result['success']
    
    # Verify role
    role = await projects.get_user_role_in_project(editor_id, project_id)
    assert role == 'viewer'
    
    # Leave project
    result = await projects.leave_project(editor_id, project_id)
    assert result['success']
    
    # Verify left
    role = await projects.get_user_role_in_project(editor_id, project_id)
    assert role is None
    
    print("✅ All tests passed!")
```

---

## Troubleshooting

### Issue: Buttons not showing

**Check:**
- Handler registered in `__init__.py`
- Callback patterns correct
- User has permission for action

### Issue: Permission denied

**Check:**
- User role in project
- Permission requirements for action
- Project membership valid

### Issue: Navigation broken

**Check:**
- Back buttons have correct callback_data
- project_id passed correctly
- Context preserved

### Issue: Invitation not working

**Check:**
- Token not expired
- User not already member
- project_invites table accessible

---

## Success Criteria

✅ **Test Passed If:**
- All scenarios complete without errors
- Permissions enforced correctly
- UI responsive and intuitive
- No data corruption
- All actions logged
- Existing features unaffected
- Mobile experience good

**Status: READY FOR TESTING** 🚀
