# Local Setup Guide

## Prerequisites

1. **Conda environment** named `telegram_bot` (already exists)
2. **PostgreSQL database** running locally or accessible
3. **Telegram Bot Token** from @BotFather

## Environment Variables

Create or update `.env` file in the project root with:

```env
# Telegram Bot Token (required)
TELEGRAM_BOT_TOKEN=your_bot_token_here

# Database Configuration (adjust to your setup)
DB_HOST=localhost
DB_PORT=5432
DB_NAME=botdb
DB_USER=bot_user
DB_PASSWORD=your_password_here

# Optional: Logging
LOG_LEVEL=INFO
LOG_FILE=
```

## Database Setup

### 1. Create Database (if not exists)

```sql
CREATE DATABASE botdb;
CREATE USER bot_user WITH PASSWORD 'your_password';
GRANT ALL PRIVILEGES ON DATABASE botdb TO bot_user;
```

### 2. Run Migration (if migrating from old system)

```bash
# Using psql
psql -U bot_user -d botdb -f migrate_to_categories.sql

# Or using Python
python -c "
import asyncio
import asyncpg
from pathlib import Path

async def run_migration():
    import os
    from dotenv import load_dotenv
    load_dotenv()
    
    dsn = f\"postgresql://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}@{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}\"
    conn = await asyncpg.connect(dsn)
    
    with open('migrate_to_categories.sql', 'r', encoding='utf-8') as f:
        await conn.execute(f.read())
    
    await conn.close()
    print('Migration completed!')

asyncio.run(run_migration())
"
```

## Running the Bot

### Windows (PowerShell/CMD)

```powershell
# Activate conda environment
conda activate telegram_bot

# Run the bot
python main.py

# Or use the batch script
.\run_bot.bat
```

### Linux/Mac

```bash
# Activate conda environment
conda activate telegram_bot

# Run the bot
python main.py

# Or use the shell script
chmod +x run_bot.sh
./run_bot.sh
```

## Verify Installation

1. **Check dependencies**:
   ```bash
   conda activate telegram_bot
   pip list | grep -E "telegram|asyncpg|pandas"
   ```

2. **Test database connection**:
   ```python
   python -c "
   import asyncio
   from utils.db import init_pool, close_pool
   async def test():
       await init_pool()
       print('Database connection OK!')
       await close_pool()
   asyncio.run(test())
   "
   ```

3. **Start bot and test**:
   - Send `/start` to your bot
   - Try `/add` command
   - Check that categories appear in inline keyboard

## Troubleshooting

### Conda not found
- Add conda to PATH or use Anaconda Prompt
- Or use full path: `C:\Users\YourUser\anaconda3\Scripts\activate.bat telegram_bot`

### Database connection error
- Check PostgreSQL is running: `pg_isready` or check service status
- Verify credentials in `.env`
- Test connection: `psql -U bot_user -d botdb -h localhost`

### Import errors
- Activate conda env: `conda activate telegram_bot`
- Install dependencies: `pip install -r requirements.txt`

### Migration errors
- Check PostgreSQL logs
- Verify database user has CREATE TABLE permissions
- Ensure old `category` column exists in expenses table before migration

## Development Tips

- Bot logs to console by default (JSON format)
- Set `LOG_FILE=logs/bot.log` in `.env` to log to file
- Use `LOG_LEVEL=DEBUG` for verbose logging
- Press Ctrl+C to stop the bot gracefully
