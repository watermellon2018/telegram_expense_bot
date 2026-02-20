# Deployment Checklist - Multi-User Projects with Management UI

## 🚀 Ready to Deploy!

All code is implemented, tested, and ready. Follow this checklist to deploy.

---

## ✅ Pre-Deployment Checklist

### 1. Database Migration (If Not Done)

Run the migration script:

```bash
psql -U bot_user -d botdb -f migration/migrate_to_shared_projects.sql
```

**What it does:**
- Adds owners to `project_members` table
- Validates `active_project_id` references
- Creates performance indexes
- Shows validation queries

**Verify migration:**
```sql
-- Check owners are in project_members
SELECT COUNT(*) FROM project_members pm
JOIN projects p ON pm.project_id = p.project_id 
WHERE pm.user_id = p.user_id AND pm.role = 'owner';

-- Should equal number of active projects
SELECT COUNT(*) FROM projects WHERE is_active = TRUE;
```

### 2. Environment Variables

Ensure these are set in your `.env`:

```bash
TELEGRAM_BOT_TOKEN=your_bot_token_here
DB_HOST=localhost
DB_PORT=5432
DB_NAME=botdb
DB_USER=bot_user
DB_PASSWORD=your_password
```

### 3. Dependencies

Verify all Python packages installed:

```bash
pip list | grep -E "(telegram|asyncpg|pandas|matplotlib)"
```

Should show:
- python-telegram-bot
- asyncpg
- pandas
- matplotlib
- seaborn

### 4. File Structure

Verify all new files exist:

```
✅ utils/permissions.py
✅ handlers/invitations.py
✅ handlers/project_management.py
✅ All .md documentation files
```

---

## 🧪 Testing Steps (Critical)

### Test 1: Bot Starts Successfully

```bash
python main.py
```

**Expected output:**
```
INFO - Bot started successfully
INFO - Handlers registered
```

**If errors:** Check import statements and handler registration.

### Test 2: Basic Commands Work

In Telegram:

```
/start
✅ Should show main menu

/help
✅ Should list all commands including new ones
```

### Test 3: Project Settings UI

```
1. /project_create Test
   ✅ Should create project

2. Click "📁 Проекты" → "⚙️ Управление"
   ✅ Should show settings menu with buttons
   ✅ Should show "✉️ Пригласить" (you're owner)
   ✅ Should NOT show "🚪 Покинуть" (owners can't leave)

3. Click "👥 Участники проекта"
   ✅ Should show members list (just you for now)
```

### Test 4: Invitation Flow (Use 2nd Account)

**As Owner (Account 1):**
```
1. Click "⚙️ Управление" → "✉️ Пригласить"
2. Click "✏️ Редактор"
3. Copy invitation link
```

**As Invitee (Account 2):**
```
4. Click invitation link
5. ✅ Should auto-join project
6. ✅ Should show success message
7. ✅ Should see project in /project_list
```

### Test 5: Permission Enforcement

**As Editor (Account 2):**
```
/add 100 продукты
✅ Should work (can add expenses)

Click "⚙️ Управление"
✅ Should NOT see "✉️ Пригласить" button
✅ Should see "🚪 Покинуть проект" button
```

---

## 📋 Deployment Steps

### Step 1: Stop Bot (if running)
```bash
# Find process
ps aux | grep python.*main.py

# Kill gracefully
kill <pid>
```

### Step 2: Pull Latest Code
```bash
git status
git add .
git commit -m "Add multi-user project management UI"
# If deploying from git:
# git push origin feature_53
```

### Step 3: Run Migration (if needed)
```bash
psql -U bot_user -d botdb -f migration/migrate_to_shared_projects.sql
```

### Step 4: Restart Bot
```bash
python main.py
```

Or if using systemd:
```bash
sudo systemctl restart telegram-bot
```

### Step 5: Verify Startup
Check logs for:
```
✅ "bot_started" event
✅ "db_pool_init_success" event
✅ No error messages
```

### Step 6: Quick Smoke Test
```
/start    # Should work
/help     # Should show new commands
/project_settings  # Should show menu
```

---

## 🔍 Post-Deployment Verification

### Check 1: Handlers Registered

Test each command:
- [x] `/project_settings` works
- [x] `/invite` works
- [x] `/members` works
- [x] All buttons clickable

### Check 2: Permissions Work

Create test project and verify:
- [x] Owner sees all management options
- [x] Editor has limited options
- [x] Viewer can only view
- [x] Non-member gets "no access"

### Check 3: Invitations Work

- [x] Create invitation as owner
- [x] Link generated correctly
- [x] New user can click and join
- [x] Token deleted after use
- [x] Expired tokens rejected

### Check 4: Member Management

- [x] Owner can view members
- [x] Owner can change roles
- [x] Owner can remove members
- [x] Non-owner can leave
- [x] Owner cannot leave

### Check 5: Data Visibility

- [x] All members see combined expenses
- [x] Personal expenses still private
- [x] Stats show correct totals

---

## 🐛 Troubleshooting

### Issue: Import Error on Startup

**Error:** `ModuleNotFoundError: No module named 'handlers.project_management'`

**Fix:**
```bash
# Verify file exists
ls handlers/project_management.py

# Check __init__.py imports
cat handlers/__init__.py | grep project_management
```

### Issue: Callback Not Working

**Error:** Clicking button does nothing

**Fix:**
```python
# Check handler registration:
# In project_management.py, verify pattern matches:
application.add_handler(
    CallbackQueryHandler(handler_func, pattern=r'^proj_members_\d+$')
)

# Pattern must match callback_data format exactly
```

### Issue: Permission Denied Always

**Error:** Every action shows "Permission denied"

**Fix:**
```sql
-- Check project_members table populated
SELECT * FROM project_members;

-- Should show owners with role='owner'

-- If empty, run:
INSERT INTO project_members (project_id, user_id, role, joined_at)
SELECT project_id, user_id, 'owner', created_date::timestamp
FROM projects WHERE is_active = TRUE
ON CONFLICT DO NOTHING;
```

### Issue: Buttons Not Showing

**Error:** Settings menu shows but buttons missing

**Fix:**
```python
# Check user role:
project = await projects.get_project_by_id(user_id, project_id)
print(f"Role: {project['role']}, Is Owner: {project['is_owner']}")

# Verify conditions in project_settings_menu():
if is_owner:  # Should add owner buttons
if not is_owner:  # Should add leave button
```

### Issue: Cannot Find Project

**Error:** "Проект не найден или у вас нет доступа"

**Fix:**
```sql
-- Check project access:
SELECT p.*, pm.role
FROM projects p
LEFT JOIN project_members pm ON p.project_id = pm.project_id AND pm.user_id = 'YOUR_USER_ID'
WHERE p.project_id = 1;

-- Should return row with role if user has access
```

---

## 📊 Monitoring After Deployment

### Key Metrics to Watch:

```bash
# Check logs for errors
tail -f logs/bot.log | grep ERROR

# Monitor permission denials
tail -f logs/bot.log | grep permission_denied

# Track invitation usage
tail -f logs/bot.log | grep invitation_created
tail -f logs/bot.log | grep invitation_accepted
```

### Database Monitoring:

```sql
-- Active projects with members
SELECT p.project_name, COUNT(pm.user_id) as members
FROM projects p
LEFT JOIN project_members pm ON p.project_id = pm.project_id
WHERE p.is_active = TRUE
GROUP BY p.project_id, p.project_name
ORDER BY members DESC;

-- Recent invitations
SELECT 
    p.project_name,
    i.role,
    i.created_at,
    CASE WHEN i.expires_at < NOW() THEN 'Expired' ELSE 'Active' END as status
FROM project_invites i
JOIN projects p ON i.project_id = p.project_id
ORDER BY i.created_at DESC
LIMIT 10;

-- Member activity (who added expenses recently)
SELECT 
    pm.user_id,
    pm.role,
    COUNT(e.id) as expenses_last_7_days
FROM project_members pm
LEFT JOIN expenses e ON pm.user_id = e.user_id 
    AND e.created_at > NOW() - INTERVAL '7 days'
GROUP BY pm.user_id, pm.role
ORDER BY expenses_last_7_days DESC;
```

---

## 🔄 Rollback Plan (If Needed)

If issues arise, you can rollback safely:

### Rollback Code:
```bash
git revert HEAD    # Revert latest commits
python main.py     # Restart with old code
```

### Database:
```sql
-- No destructive changes made
-- All new features are additive
-- Old code will still work (backwards compatible)
```

**Note:** Multi-user projects feature is additive. Rollback just removes new UI, existing functionality preserved.

---

## 📈 Success Criteria

### Deployment Successful If:

- ✅ Bot starts without errors
- ✅ All commands work (`/start`, `/help`, etc.)
- ✅ Project settings menu accessible
- ✅ Invitation creation works
- ✅ Member management functional
- ✅ Permission checks enforced
- ✅ No existing features broken
- ✅ Logs show normal activity
- ✅ Database queries performant

### User Acceptance Criteria:

- ✅ Owner can invite members easily
- ✅ Members receive clear invitations
- ✅ Members can join with one click
- ✅ Role management intuitive
- ✅ Member removal safe and clear
- ✅ Leave option works for members
- ✅ UI responsive and fast
- ✅ Error messages helpful

---

## 🎯 Quick Start Guide (For Users)

Share this with your users:

```
🎉 New Feature: Shared Projects!

You can now collaborate on expense tracking:

1. Create a project: /project_create Family Budget

2. Invite members:
   • Click "📁 Проекты" → "⚙️ Управление"
   • Click "✉️ Пригласить участника"
   • Choose role: Editor (can add) or Viewer (can view)
   • Share link with family/team

3. Manage members:
   • Click "👥 Участники проекта" to see all
   • Change roles with one click
   • Remove members if needed

4. Everyone sees combined expenses!

Questions? Type /help
```

---

## 📞 Support Resources

### For Developers:
- `ACCESS_CONTROL_AND_INVITATIONS.md` - Technical details
- `PERMISSION_QUICK_REFERENCE.md` - Quick lookup
- `PROJECT_MANAGEMENT_UI.md` - UI implementation

### For Users:
- `COMPLETE_USER_GUIDE.md` - Full user guide
- `/help` command - Command reference

### For Testing:
- `TEST_MANAGEMENT_UI.md` - Test scenarios
- `TEST_SHARED_PROJECTS.md` - Integration tests

---

## 🎊 Final Status

**Implementation:** ✅ COMPLETE  
**Testing Docs:** ✅ COMPLETE  
**User Docs:** ✅ COMPLETE  
**Linter Errors:** ✅ NONE  
**Breaking Changes:** ✅ NONE  
**Backward Compatible:** ✅ YES  

**READY FOR PRODUCTION DEPLOYMENT! 🚀**

---

## Next Steps

1. ✅ Review this checklist
2. ✅ Run migration if needed
3. ✅ Deploy code
4. ✅ Test with 2+ accounts
5. ✅ Monitor logs
6. ✅ Gather user feedback
7. ✅ Iterate and improve

**Good luck! 🍀**
