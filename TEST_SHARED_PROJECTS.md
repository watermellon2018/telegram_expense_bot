# Testing Guide: Multi-User Shared Projects

## Test Scenario 1: Create and Use Project as Owner

### Setup
```python
import asyncio
from utils import projects, excel, categories

async def test_owner_workflow():
    user_id = 12345  # Alice
    
    # 1. Create a project
    result = await projects.create_project(user_id, "Family Budget")
    assert result['success']
    project_id = result['project_id']
    print(f"✅ Created project: {project_id}")
    
    # 2. Set as active project
    result = await projects.set_active_project(user_id, project_id)
    assert result['success']
    print(f"✅ Set active project: {result['project_name']}")
    
    # 3. Create a category for this project
    result = await categories.create_category(
        user_id=user_id,
        name="Groceries",
        project_id=project_id,
        is_system=False
    )
    assert result['success']
    category_id = result['category_id']
    print(f"✅ Created category: {category_id}")
    
    # 4. Add an expense
    success = await excel.add_expense(
        user_id=user_id,
        amount=50.00,
        category_id=category_id,
        description="Weekly shopping",
        project_id=project_id
    )
    assert success
    print(f"✅ Added expense")
    
    # 5. Get monthly stats
    expenses = await excel.get_month_expenses(user_id, project_id=project_id)
    print(f"✅ Monthly total: {expenses['total']}")
    
    return project_id

# Run test
asyncio.run(test_owner_workflow())
```

## Test Scenario 2: Add Second User to Project

### Setup in Database
```sql
-- Add Bob as an editor to Alice's project
INSERT INTO project_members (project_id, user_id, role, joined_at)
VALUES (1, 67890, 'editor', NOW());
-- project_id = 1 (from previous test)
-- user_id = 67890 (Bob)
```

### Test Multi-User Access
```python
async def test_member_workflow():
    owner_id = 12345  # Alice
    member_id = 67890  # Bob
    project_id = 1  # From previous test
    
    # 1. Bob checks if he's a member
    is_member = await projects.is_project_member(member_id, project_id)
    assert is_member
    print(f"✅ Bob is a member")
    
    # 2. Bob gets his role
    role = await projects.get_user_role_in_project(member_id, project_id)
    assert role == 'editor'
    print(f"✅ Bob's role: {role}")
    
    # 3. Bob sets this project as active
    result = await projects.set_active_project(member_id, project_id)
    assert result['success']
    print(f"✅ Bob set active project: {result['project_name']}")
    
    # 4. Bob sees the project in his project list
    all_projects = await projects.get_all_projects(member_id)
    family_budget = [p for p in all_projects if p['project_id'] == project_id]
    assert len(family_budget) == 1
    assert family_budget[0]['role'] == 'editor'
    assert family_budget[0]['is_owner'] == False
    print(f"✅ Bob sees project in his list")
    
    # 5. Bob sees categories from this project (including Alice's)
    cats = await categories.get_categories_for_user_project(member_id, project_id)
    groceries = [c for c in cats if c['name'] == 'Groceries']
    assert len(groceries) == 1
    print(f"✅ Bob can see Alice's categories")
    
    # 6. Bob adds an expense to the project
    category_id = groceries[0]['category_id']
    success = await excel.add_expense(
        user_id=member_id,
        amount=30.00,
        category_id=category_id,
        description="Milk and bread",
        project_id=project_id
    )
    assert success
    print(f"✅ Bob added expense")
    
    # 7. Alice sees Bob's expense in monthly stats
    expenses = await excel.get_month_expenses(owner_id, project_id=project_id)
    assert expenses['total'] == 80.00  # Alice's 50 + Bob's 30
    print(f"✅ Alice sees combined total: {expenses['total']}")
    
    # 8. Bob also sees the combined total
    expenses = await excel.get_month_expenses(member_id, project_id=project_id)
    assert expenses['total'] == 80.00
    print(f"✅ Bob sees combined total: {expenses['total']}")
    
    # 9. Get detailed expenses (shows who added what)
    import datetime
    df = await excel.get_all_expenses(
        member_id, 
        year=datetime.datetime.now().year,
        project_id=project_id
    )
    print("\n📊 All project expenses:")
    for _, row in df.iterrows():
        print(f"  - {row['user_id']}: ${row['amount']} ({row['description']})")

asyncio.run(test_member_workflow())
```

## Test Scenario 3: Access Control

### Test Non-Member Cannot Access
```python
async def test_access_control():
    owner_id = 12345  # Alice
    member_id = 67890  # Bob
    outsider_id = 11111  # Charlie (not a member)
    project_id = 1
    
    # 1. Charlie is not a member
    is_member = await projects.is_project_member(outsider_id, project_id)
    assert not is_member
    print(f"✅ Charlie is not a member")
    
    # 2. Charlie cannot set project as active
    result = await projects.set_active_project(outsider_id, project_id)
    assert not result['success']
    print(f"✅ Charlie cannot set active project: {result['message']}")
    
    # 3. Charlie cannot see project in his list
    all_projects = await projects.get_all_projects(outsider_id)
    family_budget = [p for p in all_projects if p['project_id'] == project_id]
    assert len(family_budget) == 0
    print(f"✅ Charlie doesn't see project in his list")
    
    # 4. Charlie cannot see project stats (returns empty)
    expenses = await excel.get_month_expenses(outsider_id, project_id=project_id)
    assert expenses['total'] == 0
    print(f"✅ Charlie cannot see project expenses")
    
    # 5. Bob (editor) cannot delete the project
    result = await projects.delete_project(member_id, project_id)
    assert not result['success']
    assert 'владелец' in result['message'].lower()  # "только владелец"
    print(f"✅ Bob cannot delete project: {result['message']}")
    
    # 6. Alice (owner) can delete the project
    result = await projects.delete_project(owner_id, project_id)
    assert result['success']
    print(f"✅ Alice deleted project: {result['message']}")

asyncio.run(test_access_control())
```

## Test Scenario 4: Category Management in Shared Projects

### Test Shared Category Visibility
```python
async def test_shared_categories():
    owner_id = 12345  # Alice
    member_id = 67890  # Bob
    
    # Setup: Create project and add Bob
    result = await projects.create_project(owner_id, "Household")
    project_id = result['project_id']
    
    # Add Bob to project (SQL)
    # INSERT INTO project_members VALUES (project_id, '67890', 'editor', NOW())
    
    # 1. Alice creates a category
    result = await categories.create_category(
        user_id=owner_id,
        name="Utilities",
        project_id=project_id,
        is_system=False
    )
    alice_category_id = result['category_id']
    print(f"✅ Alice created category: {alice_category_id}")
    
    # 2. Bob sees Alice's category
    cats = await categories.get_categories_for_user_project(member_id, project_id)
    utilities = [c for c in cats if c['name'] == 'Utilities']
    assert len(utilities) == 1
    print(f"✅ Bob can see Alice's category")
    
    # 3. Bob creates his own category
    result = await categories.create_category(
        user_id=member_id,
        name="Entertainment",
        project_id=project_id,
        is_system=False
    )
    bob_category_id = result['category_id']
    print(f"✅ Bob created category: {bob_category_id}")
    
    # 4. Alice sees Bob's category
    cats = await categories.get_categories_for_user_project(owner_id, project_id)
    entertainment = [c for c in cats if c['name'] == 'Entertainment']
    assert len(entertainment) == 1
    print(f"✅ Alice can see Bob's category")
    
    # 5. Both users can use each other's categories
    success = await excel.add_expense(
        user_id=member_id,
        amount=100.00,
        category_id=alice_category_id,  # Bob using Alice's category
        description="Electric bill",
        project_id=project_id
    )
    assert success
    print(f"✅ Bob can use Alice's category")
    
    success = await excel.add_expense(
        user_id=owner_id,
        amount=50.00,
        category_id=bob_category_id,  # Alice using Bob's category
        description="Movie tickets",
        project_id=project_id
    )
    assert success
    print(f"✅ Alice can use Bob's category")

asyncio.run(test_shared_categories())
```

## Test Scenario 5: Budget Tracking in Shared Projects

### Test Budget Behavior
```python
async def test_shared_budget():
    owner_id = 12345  # Alice
    member_id = 67890  # Bob
    project_id = 1
    
    import datetime
    month = datetime.datetime.now().month
    
    # 1. Alice sets a budget for herself
    success = await excel.set_budget(
        user_id=owner_id,
        amount=500.00,
        month=month,
        project_id=project_id
    )
    assert success
    print(f"✅ Alice set budget: $500")
    
    # 2. Bob sets a different budget for himself
    success = await excel.set_budget(
        user_id=member_id,
        amount=300.00,
        month=month,
        project_id=project_id
    )
    assert success
    print(f"✅ Bob set budget: $300")
    
    # 3. Both users add expenses
    # (already added expenses in previous tests)
    
    # 4. Check budget status
    # Note: The 'actual' field shows TOTAL project spending for both users
    from utils import db
    
    alice_budget = await db.fetchrow(
        "SELECT budget, actual FROM budget WHERE user_id=$1 AND project_id=$2 AND month=$3",
        str(owner_id), project_id, month
    )
    bob_budget = await db.fetchrow(
        "SELECT budget, actual FROM budget WHERE user_id=$1 AND project_id=$2 AND month=$3",
        str(member_id), project_id, month
    )
    
    print(f"\n💰 Budget Status:")
    print(f"  Alice: Budget ${alice_budget['budget']}, Actual ${alice_budget['actual']}")
    print(f"  Bob:   Budget ${bob_budget['budget']}, Actual ${bob_budget['actual']}")
    print(f"  Note: 'Actual' shows total project spending, not individual")
    
    # Both should see the same 'actual' (total project spending)
    assert alice_budget['actual'] == bob_budget['actual']
    print(f"✅ Both users see same total spending: ${alice_budget['actual']}")

asyncio.run(test_shared_budget())
```

## SQL Queries for Manual Testing

### View Project Membership
```sql
SELECT 
    p.project_id,
    p.project_name,
    p.user_id as owner,
    pm.user_id as member,
    pm.role,
    pm.joined_at
FROM projects p
LEFT JOIN project_members pm ON p.project_id = pm.project_id
WHERE p.is_active = TRUE
ORDER BY p.project_id, pm.role DESC;
```

### View Expenses by User and Project
```sql
SELECT 
    p.project_name,
    e.user_id,
    c.name as category,
    e.amount,
    e.description,
    e.date
FROM expenses e
JOIN projects p ON e.project_id = p.project_id
JOIN categories c ON e.category_id = c.category_id
WHERE e.project_id = 1  -- Replace with your project_id
ORDER BY e.date DESC, e.user_id;
```

### Add a Member to Project
```sql
-- Add user as editor
INSERT INTO project_members (project_id, user_id, role, joined_at)
VALUES (1, '67890', 'editor', NOW());

-- Add user as viewer (read-only)
INSERT INTO project_members (project_id, user_id, role, joined_at)
VALUES (1, '11111', 'viewer', NOW());
```

### Remove a Member from Project
```sql
DELETE FROM project_members 
WHERE project_id = 1 AND user_id = '67890';
```

## Expected Behaviors Summary

### ✅ What Works Now:
1. Multiple users can be members of the same project
2. All members see combined expense totals
3. All members can add expenses (tracked by user_id)
4. All members can create and use each other's categories
5. Each member can set their own budget, but sees total spending
6. Access control prevents non-members from viewing project data
7. Only owner can delete the project

### 🔄 What's Still Per-User:
1. Budget amount (each user sets their own target)
2. Active project selection (each user has their own active project)
3. Personal expenses (project_id=NULL) remain private

### 🚧 What Requires Handler Updates:
1. Project invitation flow (generating and using invite tokens)
2. Viewing project members list
3. Removing members from project (owner only)
4. Role-based permission UI (showing what each role can do)
