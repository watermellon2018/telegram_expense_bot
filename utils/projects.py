"""
Утилиты для работы с проектами
Теперь все данные хранятся в Postgres вместо Excel.

Требования к схеме БД:
- Таблица projects: project_id, user_id, project_name, created_date, is_active
- Таблица users должна иметь колонку active_project_id (INTEGER, может быть NULL)
  Если колонки нет, выполните: ALTER TABLE users ADD COLUMN active_project_id INTEGER;
"""

import os
import datetime
import shutil
import pandas as pd
import config
from typing import Optional
from . import db

from telegram import Update
from telegram.ext import ContextTypes

async def cmd_create_project(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if not context.args:
        await update.message.reply_text("Использование: /newproject Название проекта")
        return
    
    project_name = " ".join(context.args)
    
    result = create_project(user_id, project_name)
    
    if result['success']:
        await update.message.reply_text(f"Проект создан!\nID: {result['project_id']}\nНазвание: {result['project_name']}")
    else:
        await update.message.reply_text(result['message'])


async def get_next_project_id(user_id):
    """
    Возвращает следующий доступный ID проекта
    """
    await db.execute(
        "INSERT INTO users(user_id) VALUES($1) ON CONFLICT (user_id) DO NOTHING",
        str(user_id),
    )
    
    row = await db.fetchrow(
        "SELECT COALESCE(MAX(project_id), 0) as max_id FROM projects WHERE user_id = $1",
        str(user_id),
    )
    return (row['max_id'] or 0) + 1


async def create_project(user_id: int, project_name: str) -> dict:
    await db.execute(
        "INSERT INTO users(user_id) VALUES($1) ON CONFLICT (user_id) DO NOTHING",
        str(user_id),
    )
    
    # Проверка на дубликат
    existing = await db.fetchrow(
        "SELECT project_id FROM projects WHERE user_id = $1 AND LOWER(project_name) = LOWER($2) AND is_active = TRUE",
        str(user_id), project_name
    )
    if existing:
        return {'success': False, 'message': f"Проект '{project_name}' уже существует"}
    
    project_id = await get_next_project_id(user_id)
    
    await db.execute(
        """INSERT INTO projects(project_id, user_id, project_name, created_date, is_active)
           VALUES($1, $2, $3, $4, $5)""",
        project_id, str(user_id), project_name, datetime.date.today(), True
    )
    
    # Создаём директорию (если ещё нужна для совместимости)
    from utils.excel import create_user_dir
    user_dir = create_user_dir(user_id)
    project_dir = os.path.join(user_dir, "projects", str(project_id))
    os.makedirs(project_dir, exist_ok=True)
    
    return {
        'success': True,
        'project_id': project_id,
        'project_name': project_name,
        'message': f"Проект '{project_name}' создан"
    }


async def get_all_projects(user_id: int) -> list:
    rows = await db.fetch(
        """SELECT project_id, project_name, created_date, is_active
           FROM projects WHERE user_id = $1 AND is_active = TRUE
           ORDER BY project_id""",
        str(user_id)
    )
    
    return [
        {
            'project_id': r['project_id'],
            'project_name': r['project_name'],
            'created_date': r['created_date'].strftime('%Y-%m-%d') if r['created_date'] else None,
            'is_active': r['is_active'],
        }
        for r in rows
    ]


async def get_project_by_id(user_id: int, project_id: int) -> Optional[dict]:
    row = await db.fetchrow(
        """SELECT project_id, project_name, created_date, is_active
           FROM projects WHERE user_id = $1 AND project_id = $2 AND is_active = TRUE""",
        str(user_id), project_id
    )
    if not row:
        return None
    
    return {
        'project_id': row['project_id'],
        'project_name': row['project_name'],
        'created_date': row['created_date'].strftime('%Y-%m-%d') if row['created_date'] else None,
        'is_active': row['is_active'],
    }


async def set_active_project(user_id: int, project_id: Optional[int]) -> dict:
    await db.execute(
        "INSERT INTO users(user_id) VALUES($1) ON CONFLICT (user_id) DO NOTHING",
        str(user_id),
    )
    
    if project_id is None:
        await db.execute(
            "UPDATE users SET active_project_id = NULL WHERE user_id = $1",
            str(user_id)
        )
        return {'success': True, 'project_id': None, 'message': "Переключено на общие расходы"}
    
    project = await db.fetchrow(
        "SELECT project_name FROM projects WHERE user_id = $1 AND project_id = $2 AND is_active = TRUE",
        str(user_id), project_id
    )
    if not project:
        return {'success': False, 'message': "Проект не найден"}
    
    await db.execute(
        "UPDATE users SET active_project_id = $2 WHERE user_id = $1",
        str(user_id), project_id
    )
    
    return {
        'success': True,
        'project_id': project_id,
        'project_name': project['project_name'],
        'message': f"Переключено на проект '{project['project_name']}'"
    }


async def get_active_project(user_id: int) -> Optional[dict]:
    row = await db.fetchrow(
        "SELECT active_project_id FROM users WHERE user_id = $1",
        str(user_id)
    )
    if not row or row['active_project_id'] is None:
        return None
    
    return await get_project_by_id(user_id, row['active_project_id'])