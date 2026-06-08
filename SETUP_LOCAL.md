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

### 2. Apply schema with Alembic

Схема управляется Alembic (использует те же `DB_*` из `.env`).

```bash
conda activate telegram_bot

# Новая пустая БД — создать всю схему:
alembic upgrade head

# Диагностика
alembic current        # текущая ревизия БД
alembic history        # история ревизий
alembic heads          # должен быть ровно один head
```

**Существующая БД, в которой схема уже была создана прежними `migration/*.sql`:**
пометить её базовой ревизией ОДИН раз (без выполнения DDL), затем обновлять как обычно:

```bash
alembic stamp 0001_baseline
alembic upgrade head
```

Создание новой миграции (ORM нет → `--autogenerate` не используется, DDL пишется вручную):

```bash
alembic revision -m "краткое описание"
# затем заполнить upgrade() идемпотентным SQL через op.execute(...)
alembic upgrade head
```

> При Docker-деплое миграции применяются автоматически (`alembic upgrade head`) до старта бота — см. `docker-compose.yml` (сервис `migrations`) и `.github/workflows/deploy.yml`.

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
