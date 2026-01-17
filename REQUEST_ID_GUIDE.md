# 🔍 Request ID - Production Guide

## Overview

Every Telegram update gets a **single, unique UUID-based request_id** that flows through all handlers, services, and database operations. This enables complete request tracing in logs.

## Architecture

```
Telegram Update → Middleware → Handler → Service → Database
      ↓              ↓           ↓          ↓          ↓
   update_id    request_id   request_id request_id request_id
                (UUID)       (from ctx) (passed)   (logged)
```

## Implementation

### 1. Entry Point - Middleware

**File:** `utils/logging_middleware.py`

```python
import uuid
from telegram import Update
from telegram.ext import ContextTypes

async def log_update(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Generates ONE unique request_id per Telegram update.
    Stores it in context.user_data for all handlers to access.
    """
    # Generate UUID-based request_id ONCE
    request_id = str(uuid.uuid4())
    
    # Store in context - available to ALL handlers
    context.user_data['request_id'] = request_id
    
    # Log the incoming update with request_id
    log_event(
        logger,
        "message_received",
        request_id=request_id,
        user_id=update.effective_user.id,
        status="received"
    )
```

**Key Points:**
- ✅ Generated ONCE at entry point
- ✅ UUID format: `a1b2c3d4-e5f6-7890-abcd-ef1234567890`
- ✅ Stored in `context.user_data['request_id']`
- ✅ Available to all handlers automatically

### 2. Handlers - Extract from Context

**File:** `handlers/expense.py`

```python
async def add_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handler for /add command"""
    import time
    start_time = time.time()
    
    # Extract request_id from context (generated in middleware)
    request_id = context.user_data.get('request_id')
    user_id = update.effective_user.id
    
    log_command(logger, "add", user_id=user_id, request_id=request_id)
    
    try:
        # Your business logic here
        result = await add_expense(user_id, amount, category, request_id=request_id)
        
        duration_ms = (time.time() - start_time) * 1000
        log_event(
            logger,
            "add_command_success",
            request_id=request_id,
            user_id=user_id,
            status="success",
            duration_ms=duration_ms
        )
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        log_error(
            logger,
            e,
            "add_command_error",
            request_id=request_id,
            user_id=user_id,
            duration_ms=duration_ms
        )
```

**Key Points:**
- ✅ Extract with `context.user_data.get('request_id')`
- ✅ Pass to services/utilities
- ✅ Include in all log calls
- ✅ Never generate a new one

### 3. Services - Receive as Parameter

**File:** `utils/excel.py`

```python
async def add_expense(
    user_id: int,
    amount: float,
    category: str,
    description: str = "",
    project_id: Optional[int] = None,
    request_id: Optional[str] = None
) -> bool:
    """
    Adds expense to database.
    
    Args:
        user_id: User ID
        amount: Expense amount
        category: Category name
        description: Optional description
        project_id: Optional project ID
        request_id: Request ID for tracing (from context)
    """
    import time
    start_time = time.time()
    
    log_event(
        expense_logger,
        "add_expense_start",
        request_id=request_id,
        user_id=user_id,
        amount=amount,
        category=category
    )
    
    try:
        # Call database with request_id
        await db.execute(
            "INSERT INTO expenses (...) VALUES (...)",
            user_id, amount, category,
            request_id=request_id  # Pass to DB layer
        )
        
        duration_ms = (time.time() - start_time) * 1000
        log_event(
            expense_logger,
            "add_expense_success",
            request_id=request_id,
            user_id=user_id,
            status="success",
            duration_ms=duration_ms
        )
        return True
        
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        log_error(
            expense_logger,
            e,
            "add_expense_error",
            request_id=request_id,
            user_id=user_id,
            duration_ms=duration_ms
        )
        return False
```

**Key Points:**
- ✅ Accept `request_id` as optional parameter
- ✅ Pass to database operations
- ✅ Include in all logs
- ✅ Never generate a new one

### 4. Database - Include in Logs

**File:** `utils/db.py`

```python
async def execute(query: str, *args, request_id: str = None):
    """
    Executes SQL query (INSERT, UPDATE, DELETE)
    
    Args:
        query: SQL query
        *args: Query parameters
        request_id: Request ID for tracing (optional)
    """
    import time
    start_time = time.time()
    
    try:
        result = await _pool.execute(query, *args)
        duration = time.time() - start_time
        
        operation = query.strip().split()[0].upper()
        table = extract_table_name(query)
        
        log_database_operation(
            db_logger,
            operation,
            table=table,
            duration=duration,
            request_id=request_id  # Include in log
        )
        
        return result
        
    except Exception as e:
        duration = time.time() - start_time
        log_error(
            db_logger,
            e,
            "db_execute_error",
            request_id=request_id,  # Include in error log
            duration_ms=duration * 1000,
            operation=operation,
            table=table
        )
        raise
```

**Key Points:**
- ✅ Accept `request_id` as optional parameter
- ✅ Include in all database operation logs
- ✅ Include in error logs
- ✅ Never generate a new one

## Log Examples

### Complete Request Trace

```
[2026-01-16T20:00:00.100Z] INFO  [telegram.updates] message_received       request_id=a1b2c3d4-e5f6-7890-abcd-ef1234567890 user_id=456 status=received
[2026-01-16T20:00:00.105Z] INFO  [handlers.expense] command_executed       request_id=a1b2c3d4-e5f6-7890-abcd-ef1234567890 user_id=456 command=add
[2026-01-16T20:00:00.110Z] INFO  [utils.excel     ] add_expense_start      request_id=a1b2c3d4-e5f6-7890-abcd-ef1234567890 user_id=456 amount=100.0
[2026-01-16T20:00:00.120Z] INFO  [utils.db        ] database_operation     request_id=a1b2c3d4-e5f6-7890-abcd-ef1234567890 action=INSERT table=expenses duration_ms=8.5
[2026-01-16T20:00:00.125Z] INFO  [utils.excel     ] add_expense_success    request_id=a1b2c3d4-e5f6-7890-abcd-ef1234567890 user_id=456 status=success duration_ms=15.0
[2026-01-16T20:00:00.130Z] INFO  [handlers.expense] add_command_success    request_id=a1b2c3d4-e5f6-7890-abcd-ef1234567890 user_id=456 status=success duration_ms=30.0
```

**Same request_id in ALL logs!**

### JSON Format

```json
{"timestamp":"2026-01-16T20:00:00.100Z","level":"INFO","service":"telegram.updates","event":"message_received","request_id":"a1b2c3d4-e5f6-7890-abcd-ef1234567890","user_id":456,"status":"received"}
{"timestamp":"2026-01-16T20:00:00.105Z","level":"INFO","service":"handlers.expense","event":"command_executed","request_id":"a1b2c3d4-e5f6-7890-abcd-ef1234567890","user_id":456,"command":"add"}
{"timestamp":"2026-01-16T20:00:00.110Z","level":"INFO","service":"utils.excel","event":"add_expense_start","request_id":"a1b2c3d4-e5f6-7890-abcd-ef1234567890","user_id":456,"amount":100.0}
{"timestamp":"2026-01-16T20:00:00.120Z","level":"INFO","service":"utils.db","event":"database_operation","request_id":"a1b2c3d4-e5f6-7890-abcd-ef1234567890","action":"INSERT","table":"expenses","duration_ms":8.5}
```

## Analysis

### Find all logs for a request:
```bash
# Grep
grep "request_id=a1b2c3d4-e5f6-7890-abcd-ef1234567890" logs.txt

# jq (JSON)
jq 'select(.request_id=="a1b2c3d4-e5f6-7890-abcd-ef1234567890")' logs.json
```

### Find slow requests:
```bash
jq 'select(.duration_ms > 100) | .request_id' logs.json | sort | uniq
```

### Trace specific user's requests:
```bash
jq 'select(.user_id==456) | .request_id' logs.json | sort | uniq
```

## Best Practices

### ✅ DO

1. **Generate ONCE** - Only in middleware
2. **Store in context** - `context.user_data['request_id']`
3. **Extract in handlers** - `context.user_data.get('request_id')`
4. **Pass as parameter** - To services and utilities
5. **Include in ALL logs** - Every log_event, log_error, etc.
6. **Optional parameter** - Use `request_id: Optional[str] = None`

### ❌ DON'T

1. **Generate in handlers** - Only middleware generates
2. **Generate in services** - Only receive as parameter
3. **Generate in database layer** - Only receive as parameter
4. **Skip in logs** - Always include if available
5. **Use update_id** - Use UUID instead

## Code Checklist

When adding new handlers/services:

- [ ] Extract `request_id` from context in handler
- [ ] Pass `request_id` to service functions
- [ ] Add `request_id` parameter to service signatures
- [ ] Include `request_id` in all log calls
- [ ] Pass `request_id` to database operations
- [ ] Handle `request_id=None` gracefully (for backward compatibility)

## Testing

```python
# Mock context with request_id
mock_context.user_data = {'request_id': 'test-uuid-1234'}

# Verify it's passed to services
await add_expense(
    user_id=123,
    amount=100.0,
    category="food",
    request_id=mock_context.user_data.get('request_id')
)

# Check logs contain request_id
assert "request_id=test-uuid-1234" in captured_logs
```

## Benefits

✅ **Complete tracing** - See entire request flow
✅ **Error debugging** - Find all related logs instantly
✅ **Performance analysis** - Track slow requests end-to-end
✅ **Monitoring** - Group metrics by request
✅ **Production-ready** - UUID format, clean code
✅ **Minimal overhead** - Generate once, pass everywhere

## Summary

```python
# 1. Middleware - Generate ONCE
request_id = str(uuid.uuid4())
context.user_data['request_id'] = request_id

# 2. Handler - Extract from context
request_id = context.user_data.get('request_id')

# 3. Service - Receive as parameter
async def my_service(user_id, request_id=None):
    log_event(logger, "event", request_id=request_id)

# 4. Database - Include in logs
async def execute(query, *args, request_id=None):
    log_database_operation(..., request_id=request_id)
```

Clean, minimal, production-ready! 🚀
