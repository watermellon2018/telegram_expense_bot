# Complete User Guide - Multi-User Project Management

## 📖 Overview

Your Telegram expense bot now supports shared projects with full member management, role-based permissions, and invitation system. Multiple users can collaborate on tracking expenses together.

---

## 🚀 Getting Started

### For New Users:

1. **Start the bot:** `/start`
2. **Create your first project:** 
   - Click "📁 Проекты" → "🆕 Создать проект"
   - Enter project name (e.g., "Family Budget")
3. **Add expenses:** Use `/add` or click "➕ Добавить"

### For Invited Users:

1. **Click invitation link** (received from project owner)
2. **Automatic setup:** Bot adds you to project and sets it as active
3. **Start using:** Add expenses, view stats based on your role

---

## 👥 User Roles

### 👑 Owner (Project Creator)
**Full Control:**
- ✅ Add, edit, delete expenses
- ✅ Create, edit, delete categories
- ✅ Set budgets
- ✅ View all stats and history
- ✅ Invite members
- ✅ Remove members
- ✅ Change member roles
- ✅ Delete project
- ❌ Cannot leave (must delete project instead)

### ✏️ Editor (Collaborator)
**Can Modify Data:**
- ✅ Add, edit, delete expenses
- ✅ Create, edit, delete categories
- ✅ Set budgets
- ✅ View all stats and history
- ✅ Leave project
- ❌ Cannot invite/remove members
- ❌ Cannot change roles
- ❌ Cannot delete project

### 👁️ Viewer (Observer)
**Read-Only:**
- ✅ View all stats and history
- ✅ View members list
- ✅ View budgets
- ✅ Leave project
- ❌ Cannot add/edit expenses
- ❌ Cannot modify categories
- ❌ Cannot manage members

---

## 🎯 Common Tasks

### Task 1: Invite Someone to Your Project

**As Owner:**

1. Make sure project is active
2. **Option A: Use UI**
   - Click "📁 Проекты" → "⚙️ Управление"
   - Click "✉️ Пригласить участника"
   - Select role: ✏️ Редактор or 👁️ Наблюдатель
   - Copy and share link

3. **Option B: Use Command**
   ```
   /invite editor
   ```
   or
   ```
   /invite viewer
   ```

**Invitation Link:**
```
https://t.me/your_bot?start=inv_abc123...xyz
```

**Expiration:** 24 hours

---

### Task 2: View Project Members

**As Any Member:**

1. **Option A: Use UI**
   - Click "📁 Проекты" → "⚙️ Управление"
   - Click "👥 Участники проекта"

2. **Option B: Use Command**
   ```
   /members
   ```

**What You'll See:**
```
📁 Family Budget

👥 Участники (3):

👑 Владелец
ID: 12345 (владелец)
Присоединился: 2026-01-15

✏️ Редактор
ID: 67890
Присоединился: 2026-02-01

👁️ Наблюдатель
ID: 11111
Присоединился: 2026-02-01
```

---

### Task 3: Change Someone's Role

**As Owner:**

1. Click "📁 Проекты" → "⚙️ Управление"
2. Click "⚙️ Управление ролями"
3. Click "↔️ Изменить на [new role]" next to member
4. Role changes immediately

**Role Toggle:**
- Editor → Viewer
- Viewer → Editor

---

### Task 4: Remove Someone from Project

**As Owner:**

1. Click "📁 Проекты" → "⚙️ Управление"
2. Click "👥 Участники проекта"
3. Click "❌ Удалить" next to member
4. Confirm removal
5. Member immediately loses access

**Cannot Remove:**
- Yourself (owner)
- Other owners (only one owner per project)

---

### Task 5: Leave a Project

**As Editor or Viewer:**

1. Click "📁 Проекты" → "⚙️ Управление"
2. Click "🚪 Покинуть проект"
3. Confirm leaving
4. You lose access immediately

**Owner Restriction:**
Owners cannot leave. To stop managing a project:
- Delete the project, or
- Transfer ownership (future feature)

---

### Task 6: Add Expense to Shared Project

**As Owner or Editor:**

1. Make sure project is active
2. Add expense as usual:
   ```
   /add 100 продукты молоко
   ```
   or
   ```
   100 продукты молоко
   ```

**Result:**
- Expense recorded with your user_id
- Visible to all project members
- Counts toward project totals

**As Viewer:**
- Cannot add expenses
- Will get permission denied error

---

### Task 7: View Project Statistics

**As Any Member:**

```
/month    # Current month stats
/day      # Today's stats
/stats    # Annual charts
```

**What You'll See:**
- Combined expenses from ALL project members
- Your contributions tracked by user_id
- Total project spending

---

## 🎛️ Project Settings Menu

### Access:
- Command: `/project_settings`
- Button: "⚙️ Управление" in Projects menu

### Menu Options:

#### For Owners:
```
⚙️ Управление проектом

📁 Family Budget
👑 Владелец

📊 Статистика:
• Расходов: 45
• Сумма: 5230.50
• Участников: 3

[👥 Участники проекта]
[✉️ Пригласить участника]
[⚙️ Управление ролями]
```

#### For Editors:
```
⚙️ Управление проектом

📁 Family Budget
✏️ Редактор

📊 Статистика:
• Расходов: 45
• Сумма: 5230.50
• Участников: 3

[👥 Участники проекта]
[🚪 Покинуть проект]
```

#### For Viewers:
```
⚙️ Управление проектом

📁 Family Budget
👁️ Наблюдатель

📊 Статистика:
• Расходов: 45
• Сумма: 5230.50
• Участников: 3

[👥 Участники проекта]
[🚪 Покинуть проект]
```

---

## 📱 UI Navigation Map

```
Main Menu (⬅️ Главное меню)
│
├─ 📁 Проекты
│  ├─ 🆕 Создать проект
│  ├─ 📋 Список проектов
│  ├─ 🔄 Выбрать проект
│  ├─ 📊 Общие расходы
│  ├─ ℹ️ Инфо о проекте
│  │  └─ [⚙️ Управление проектом] (inline button)
│  ├─ ⚙️ Управление ⭐ NEW
│  │  ├─ 👥 Участники проекта
│  │  │  ├─ [🔄 Роль] (owner only)
│  │  │  ├─ [❌ Удалить] (owner only)
│  │  │  └─ [« Назад]
│  │  ├─ ✉️ Пригласить участника (owner only)
│  │  │  ├─ [✏️ Редактор]
│  │  │  ├─ [👁️ Наблюдатель]
│  │  │  └─ Shows invitation link
│  │  ├─ ⚙️ Управление ролями (owner only)
│  │  │  ├─ [↔️ Изменить роль]
│  │  │  └─ [« Назад]
│  │  └─ 🚪 Покинуть проект (non-owners only)
│  │     └─ Confirmation dialog
│  ├─ 🗑️ Удалить проект
│  └─ ⬅️ Главное меню
│
├─ ➕ Добавить (expense)
├─ 📅 Месяц (stats)
├─ 📆 День (stats)
├─ 📈 Статистика
├─ 📂 Категории
├─ 📤 Экспорт
└─ ❓ Помощь
```

---

## 🔐 Security & Privacy

### What's Secure:
✅ Invitation tokens cryptographically random  
✅ Tokens expire after 24 hours  
✅ One-time use (deleted after acceptance)  
✅ Permission checks on all operations  
✅ Cannot access projects you're not member of  
✅ Cannot bypass permissions via commands  

### What's Private:
✅ Personal expenses (no project) - always private  
✅ Only project members see project data  
✅ User IDs tracked for attribution  

### What's Shared (in projects):
📊 All members see ALL project expenses  
📊 All members see ALL project categories  
📊 All members see combined totals  
📊 All members see member list  

---

## 💡 Tips & Best Practices

### For Project Owners:

1. **Start with Editors** - Invite trusted members as Editors first
2. **Use Viewers for Reports** - Add stakeholders as Viewers for transparency
3. **Regular Review** - Check member list periodically
4. **Remove Inactive** - Remove members who no longer need access
5. **Clear Roles** - Communicate expectations for each role

### For Project Members:

1. **Check Your Role** - Use `/project_info` to see your permissions
2. **Ask Before Leaving** - Coordinate with owner before leaving
3. **Respect Permissions** - Don't try to bypass restrictions
4. **Track Attribution** - Your user_id is recorded with each expense

### For Teams:

1. **Single Active Project** - Keep one project active at a time
2. **Consistent Categories** - Agree on category usage
3. **Regular Check-ins** - Review stats together
4. **Budget Coordination** - Set individual budgets, track collective spending

---

## ❓ FAQ

### Q: Can I be a member of multiple projects?
**A:** Yes! You can be a member (or owner) of unlimited projects. Switch between them with `/project_select`.

### Q: What happens to my expenses if I leave a project?
**A:** Your expenses remain in the project. Other members can still see them. You just lose access.

### Q: Can I rejoin a project after leaving?
**A:** Yes, if the owner sends you a new invitation link.

### Q: What if the owner leaves?
**A:** Owners cannot leave. They must either delete the project or transfer ownership (future feature).

### Q: Can I see who added each expense?
**A:** Yes, each expense tracks the user_id of who added it (visible in exports and detailed views).

### Q: What happens to invitations after 24 hours?
**A:** They expire and cannot be used. A cleanup task removes expired invitations daily.

### Q: Can the same invitation be used multiple times?
**A:** No, invitations are one-time use and deleted after acceptance.

### Q: Can I change my own role?
**A:** No, only the project owner can change roles.

### Q: What if I accidentally kick someone?
**A:** You'll need to create a new invitation for them. There's no "undo" for removal.

### Q: Do personal expenses (no project) still work?
**A:** Yes! Personal expenses are completely separate and always private.

---

## 🎯 Complete Example Workflow

### Alice Creates Family Budget Project:

```
1. Alice: /project_create Family Budget
   ✅ Проект создан и активирован

2. Alice: Click "⚙️ Управление"
   → Opens project settings

3. Alice: Click "✉️ Пригласить участника"
   → Select "✏️ Редактор"
   → Gets link: https://t.me/bot?start=inv_xyz...

4. Alice: Shares link with Bob (husband)
```

### Bob Joins as Editor:

```
5. Bob: Clicks invitation link
   ✅ Вы добавлены в проект 'Family Budget' с ролью 'editor'
   
6. Bob: /add 50 продукты groceries
   ✅ Расход добавлен
   
7. Alice: /month
   📊 Видит расходы Bob'а в общей статистике
```

### Alice Invites Carol as Viewer:

```
8. Alice: Click "⚙️ Управление" → "✉️ Пригласить"
   → Select "👁️ Наблюдатель"
   → Shares link with Carol (mother-in-law)

9. Carol: Clicks link
   ✅ Вы добавлены в проект 'Family Budget' с ролью 'viewer'

10. Carol: /month
    ✅ Can view all expenses

11. Carol: /add 100 продукты
    ❌ У вас нет прав на добавление расходов
```

### Alice Reviews Team:

```
12. Alice: Click "⚙️ Управление" → "👥 Участники"
    Sees:
    - Alice (Owner)
    - Bob (Editor) [🔄] [❌]
    - Carol (Viewer) [🔄] [❌]

13. Alice: Clicks "🔄 Роль" for Carol
    → Changes Carol to Editor

14. Carol: /add 100 продукты
    ✅ Расход добавлен (now has permission)
```

### Bob Leaves Project:

```
15. Bob: Click "⚙️ Управление" → "🚪 Покинуть проект"
    → Confirms leaving
    ✅ Вы покинули проект 'Family Budget'

16. Bob: /month
    → No longer sees Family Budget data
    → His expenses still in project, but he can't access
```

---

## 🖥️ All Available Commands

### Project Management:
```
/project_create <name>       Create new project
/project_list                List all your projects
/project_select <name|id>    Switch to project
/project_main                Switch to personal expenses
/project_info                Show current project info
/project_delete <name|id>    Delete project (owner only)
/project_settings            Project settings menu ⭐ NEW
```

### Member Management:
```
/invite [role]               Create invitation (owner only)
/members                     List project members
```

### Expenses & Stats:
```
/add <amount> <category> [desc]  Add expense
/month                           Monthly stats
/day                             Daily stats
/stats                           Annual charts
/category [name]                 Category stats
/export                          Export to Excel
```

### Categories:
```
Click "📂 Категории" button for category menu
```

### Help:
```
/help                        Show all commands
```

---

## 🎨 UI Components

### Main Menu Buttons:
```
➕ Добавить    📅 Месяц     📆 День      📈 Статистика
📂 Категории   📤 Экспорт   📁 Проекты   ❓ Помощь
```

### Projects Menu Buttons:
```
🆕 Создать     📋 Список
🔄 Выбрать     📊 Общие
ℹ️ Инфо        ⚙️ Управление ⭐
🗑️ Удалить     ⬅️ Главное
```

### Project Settings (Inline Buttons):
- Owner: [👥 Участники] [✉️ Пригласить] [⚙️ Роли]
- Non-owner: [👥 Участники] [🚪 Покинуть]

---

## 📊 Data Visibility

### In Projects (Shared):
- ✅ All members see ALL expenses
- ✅ All members see combined totals
- ✅ All members see each other's categories
- ✅ Each expense tracks who added it
- ✅ Budget tracking shows total project spending

### Personal (No Project):
- ✅ Only you see your personal expenses
- ✅ Completely separate from projects
- ✅ Not shared with anyone

---

## 🔄 Switching Contexts

### Between Projects:
```
/project_select <name or id>
```

### To Personal Expenses:
```
/project_main
```
or click "📊 Общие расходы"

### Check Current Context:
```
/project_info
```

**Active Indicator:**
- Project list shows "(активен)" next to active project
- Stats commands use active project automatically

---

## ⚠️ Important Notes

### Ownership:
- Each project has exactly ONE owner
- Owner is the user who created the project
- Owner cannot change (yet - transfer coming in future)
- Owner cannot be removed or downgraded

### Leaving:
- Non-owners can leave anytime
- Owners cannot leave (must delete project)
- Leaving doesn't delete your past expenses
- Can rejoin via new invitation

### Removal:
- Only owner can remove members
- Removal is immediate
- Removed members lose all access
- Must be re-invited to rejoin

### Invitations:
- One-time use only
- Expire after 24 hours
- Cannot be reused after acceptance
- Cannot be cancelled (yet)

### Data Attribution:
- Each expense records who added it
- Cannot be changed after creation
- Visible in detailed exports
- Useful for accountability

---

## 🛠️ Troubleshooting

### "Нет активного проекта"
**Solution:** Select a project first:
```
/project_select <project name>
```

### "У вас нет прав на операцию"
**Solution:** Check your role:
```
/project_info
```
Viewers cannot modify data. Ask owner to upgrade you to Editor.

### "Приглашение истекло"
**Solution:** Ask project owner to create a new invitation.

### "Проект не найден"
**Solution:** 
1. Check project list: `/project_list`
2. Verify you're a member
3. Verify project wasn't deleted

### Owner wants to leave
**Solution:** Owner cannot leave. Options:
1. Delete project: `/project_delete <name>`
2. Wait for ownership transfer feature

---

## 📈 Best Practices

### Team Collaboration:

1. **Assign Appropriate Roles**
   - Active participants → Editor
   - Observers/stakeholders → Viewer
   - Trust → Owner (cannot be changed)

2. **Regular Reviews**
   - Check member list monthly
   - Remove inactive members
   - Verify roles still appropriate

3. **Clear Communication**
   - Inform members of role changes
   - Announce when removing someone
   - Set expectations for data entry

4. **Budget Coordination**
   - Each member sets their own budget
   - Collectively track total spending
   - Discuss overages as a team

5. **Category Consistency**
   - Agree on category usage
   - Use standard names
   - Don't create duplicates

---

## 🎉 What's New in This Release

### ✅ New Features:
1. **Visual Management UI** - Button-based project management
2. **Member List with Actions** - Inline buttons for kick/role change
3. **Quick Invitations** - One-click invitation generation
4. **Role Management** - Visual role toggle interface
5. **Leave Project** - Self-service exit for members
6. **Enhanced Info** - Projects show your role
7. **Permission Integration** - All UI respects permissions

### ✅ Improvements:
- Better UX with inline keyboards
- Real-time updates
- Confirmation dialogs for safety
- Role indicators everywhere
- Mobile-friendly interface

### ✅ No Breaking Changes:
- All existing commands work
- Personal expenses unchanged
- Backward compatible

---

## 📞 Support

### Documentation:
- **Technical:** See `ACCESS_CONTROL_AND_INVITATIONS.md`
- **Developer:** See `PERMISSION_QUICK_REFERENCE.md`
- **Testing:** See `TEST_MANAGEMENT_UI.md`

### Commands:
```
/help    # Show all available commands
```

---

**Version:** 2.0 - Multi-User Projects with Management UI  
**Status:** Production Ready ✅  
**Last Updated:** February 2026
