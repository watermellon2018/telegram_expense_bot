# 🧪 Testing Guide

## Quick Start

### Run All Tests
```bash
C:\Users\stepa\miniconda3\envs\telegram_bot\python.exe -m pytest
```

### Run with Coverage Report
```bash
C:\Users\stepa\miniconda3\envs\telegram_bot\python.exe -m pytest --cov=handlers --cov=utils --cov-report=html
```

### View Coverage Report
```bash
start htmlcov/index.html
```

### Run Specific Tests
```bash
# Run specific file
C:\Users\stepa\miniconda3\envs\telegram_bot\python.exe -m pytest tests/test_handlers_export.py

# Run specific test
C:\Users\stepa\miniconda3\envs\telegram_bot\python.exe -m pytest tests/test_handlers_export.py::test_export_command_no_args_shows_menu

# Run tests matching pattern
C:\Users\stepa\miniconda3\envs\telegram_bot\python.exe -m pytest -k "export"
```

## Test Results

✅ **33/33 tests passing** (100%)
📊 **Code coverage: 25%**

### Test Coverage by Module

| Module | Coverage | Notes |
|--------|----------|-------|
| handlers/start.py | 89% | ✅ Well tested |
| handlers/expense.py | 51% | 🟡 Core flows covered |
| handlers/export.py | 42% | 🟡 Main features tested |
| handlers/project.py | 11% | 🔴 Needs more tests |
| handlers/stats.py | 13% | 🔴 Needs more tests |
| utils/helpers.py | 34% | 🟡 Key functions tested |
| utils/db.py | 43% | 🟡 Core operations covered |

## Test Structure

```
tests/
├── __init__.py                   # Test package
├── conftest.py                   # Shared fixtures & test utilities
├── test_handlers_start.py        # /start, /help, menus
├── test_handlers_expense.py      # /add, expense tracking
├── test_handlers_export.py       # /export, interactive menus
└── test_utils_helpers.py         # Helper functions
```

## Adding New Tests

When you add a new feature:

```python
# tests/test_new_feature.py
import pytest
from unittest.mock import patch, AsyncMock

@pytest.mark.asyncio
async def test_my_feature(mock_update, mock_context):
    """Test description"""
    # Arrange
    mock_context.args = ["test_arg"]
    
    # Act
    with patch('your.module.function', new=AsyncMock(return_value="result")):
        await your_handler(mock_update, mock_context)
    
    # Assert
    mock_update.message.reply_text.assert_called_once()
```

## Available Fixtures

From `conftest.py`:
- `mock_user` - Mock Telegram user
- `mock_chat` - Mock Telegram chat
- `mock_message` - Mock Telegram message
- `mock_callback_query` - Mock inline button callback
- `mock_update` - Mock Update (with message)
- `mock_update_with_callback` - Mock Update (with callback query)
- `mock_context` - Mock bot context
- `test_user_id` - Test user ID (123456789)
- `test_project_id` - Test project ID (1)

## CI/CD

Tests automatically run on:
- Push to `master` or `dev` branch
- Pull requests to `master` or `dev`
- Tested on Python 3.9, 3.10, 3.11

## Before Committing

Always run tests:
```bash
C:\Users\stepa\miniconda3\envs\telegram_bot\python.exe -m pytest
```

## Troubleshooting

### Tests fail with import errors
```bash
# Install test dependencies
C:\Users\stepa\miniconda3\envs\telegram_bot\python.exe -m pip install -r requirements-dev.txt
```

### Need to debug a test
```bash
# Run with verbose output and stop at first failure
C:\Users\stepa\miniconda3\envs\telegram_bot\python.exe -m pytest -vvs -x
```

### Test runs but doesn't cover my code
Check if your code needs database mocking:
```python
with patch('module.db.fetch', new=AsyncMock(return_value=mock_data)):
    # your test
```
