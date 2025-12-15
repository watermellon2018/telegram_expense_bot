import asyncio
import asyncpg
import os
import pandas as pd
from pathlib import Path
from urllib.parse import quote_plus
from datetime import datetime, date, time



# --- Настройки подключения ---
DB_HOST = os.environ.get("DB_HOST", "postgres_server")
DB_PORT = os.environ.get("DB_PORT", "5432")
DB_NAME = os.environ.get("DB_NAME", "botdb")
DB_USER = os.environ.get("DB_USER", "bot_user")
DB_PASSWORD = os.environ.get("DB_PASSWORD")
USERS_FOLDER = os.environ.get("USERS_FOLDER", "users")

DATABASE_URL = f"postgresql://{DB_USER}:{quote_plus(DB_PASSWORD)}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
USERS_FOLDER = os.path.expanduser(USERS_FOLDER)


def safe_str(val):
    """Конвертируем значение в строку для asyncpg, пустое или NaN → None"""
    if pd.isna(val):
        return None
    return str(val)


def parse_date(val):
    """Конвертируем строку или pd.Timestamp в datetime.date"""
    if pd.isna(val):
        return None
    if isinstance(val, date):
        return val
    if isinstance(val, pd.Timestamp):
        return val.date()
    if isinstance(val, str):
        return datetime.strptime(val, "%Y-%m-%d").date()
    raise ValueError(f"Cannot convert {val} to date")

def parse_time(val):
    """Конвертируем строку или pd.Timestamp в datetime.time"""
    if pd.isna(val):
        return None
    if isinstance(val, time):
        return val
    if isinstance(val, pd.Timestamp):
        return val.time()
    if isinstance(val, str):
        return datetime.strptime(val, "%H:%M:%S").time()
    raise ValueError(f"Cannot convert {val} to time")


# --- Миграция одного пользователя ---
async def migrate_user(conn, user_folder: Path):
    user_id = user_folder.name
    print(f"Migrating user {user_id}")
    
    # 1. Добавляем пользователя
    await conn.execute(
        "INSERT INTO users(user_id) VALUES($1) ON CONFLICT (user_id) DO NOTHING",
        user_id
    )
    
    # 2. Миграция 2025.xlsx (Expenses и Budget)
    user_excel = user_folder / "2025.xlsx"
    if user_excel.exists():
        # Expenses
        df_exp = pd.read_excel(user_excel, sheet_name="Expenses")
        for row in df_exp.to_dict(orient="records"):
            await conn.execute(
                """INSERT INTO expenses(user_id, project_id, date, time, amount, category, description, month)
                   VALUES($1, NULL, $2, $3, $4, $5, $6, $7)""",
                user_id,
                parse_date(row["date"]),
                parse_time(row["time"]),
                row["amount"],
                row.get("category"),
                safe_str(row.get("description")),
                row["month"]
            )
        # Budget
        df_budget = pd.read_excel(user_excel, sheet_name="Budget")
        for row in df_budget.to_dict(orient="records"):
            await conn.execute(
                """INSERT INTO budget(user_id, project_id, month, budget, actual)
                   VALUES($1, NULL, $2, $3, $4)""",
                user_id,
                row["month"],
                row["budget"],
                row["actual"]
            )
    
    # 3. Миграция проектов пользователя
    projects_file = user_folder / "projects.xlsx"
    if projects_file.exists():
        df_projects = pd.read_excel(projects_file, sheet_name="Projects")
        for row in df_projects.to_dict(orient="records"):
            row["created_date"] = parse_date(row["created_date"])
            project_id = row["project_id"]
            is_active = True if str(row["is_active"]).upper() in ("ИСТИНА", "TRUE", "1") else False
            await conn.execute(
                """INSERT INTO projects(project_id, user_id, project_name, created_date, is_active)
                   VALUES($1, $2, $3, $4, $5)
                   ON CONFLICT (project_id, user_id) DO NOTHING""",
                project_id,
                user_id,
                row["project_name"],
                row["created_date"],
                is_active
            )
            
            # 4. Миграция Excel проекта
            project_folder = user_folder / "projects" / str(project_id)
            if project_folder.exists():
                # Находим Excel файл в папке проекта (любой .xlsx)
                excel_files = list(project_folder.glob("*.xlsx"))
                if not excel_files:
                    continue
                project_excel = excel_files[0]
                
                # Expenses
                df_exp_proj = pd.read_excel(project_excel, sheet_name="Expenses")
                for r in df_exp_proj.to_dict(orient="records"):
                    await conn.execute(
                        """INSERT INTO expenses(user_id, project_id, date, time, amount, category, description, month)
                           VALUES($1, $2, $3, $4, $5, $6, $7, $8)""",
                        user_id,
                        project_id,
                        parse_date(r["date"]),
                        parse_time(r["time"]),
                        r["amount"],
                        r.get("category"),
                        safe_str(r.get("description")),
                        r["month"]
                    )
                # Budget
                df_budget_proj = pd.read_excel(project_excel, sheet_name="Budget")
                for r in df_budget_proj.to_dict(orient="records"):
                    await conn.execute(
                        """INSERT INTO budget(user_id, project_id, month, budget, actual)
                           VALUES($1, $2, $3, $4, $5)""",
                        user_id,
                        project_id,
                        r["month"],
                        r["budget"],
                        r["actual"]
                    )

# --- Основная функция ---
async def main():
    conn = await asyncpg.connect(DATABASE_URL)
    users_path = Path(USERS_FOLDER)
    
    for user_folder in users_path.iterdir():
        if user_folder.is_dir():
            await migrate_user(conn, user_folder)
    
    await conn.close()
    print("Migration finished!")

# --- Запуск ---
if __name__ == "__main__":
    asyncio.run(main())
