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
from . import db

def get_next_project_id(user_id):
    """
    Возвращает следующий доступный ID проекта
    """
    async def _do():
        # Убедимся, что пользователь существует
        await db.execute(
            "INSERT INTO users(user_id) VALUES($1) ON CONFLICT (user_id) DO NOTHING",
            str(user_id),
        )
        
        # Получаем максимальный project_id для этого пользователя
        row = await db.fetchrow(
            "SELECT COALESCE(MAX(project_id), 0) as max_id FROM projects WHERE user_id = $1",
            str(user_id),
        )
        return (row['max_id'] or 0) + 1
    
    try:
        return db.run_async(_do())
    except Exception as e:
        print(f"Ошибка при получении следующего ID проекта: {e}")
        return 1

def create_project(user_id, project_name):
    """
    Создает новый проект
    """
    async def _do():
        # Убедимся, что пользователь существует
        await db.execute(
            "INSERT INTO users(user_id) VALUES($1) ON CONFLICT (user_id) DO NOTHING",
            str(user_id),
        )
        
        # Проверяем, существует ли проект с таким именем
        existing = await db.fetchrow(
            "SELECT project_id FROM projects WHERE user_id = $1 AND LOWER(project_name) = LOWER($2) AND is_active = TRUE",
            str(user_id),
            project_name,
        )
        
        if existing:
            return {
                'success': False,
                'message': f"Проект '{project_name}' уже существует"
            }
        
        # Получаем следующий ID
        row = await db.fetchrow(
            "SELECT COALESCE(MAX(project_id), 0) as max_id FROM projects WHERE user_id = $1",
            str(user_id),
        )
        project_id = (row['max_id'] or 0) + 1
        
        # Создаем новую запись
        created_date = datetime.datetime.now().date()
        await db.execute(
            """INSERT INTO projects(project_id, user_id, project_name, created_date, is_active)
               VALUES($1, $2, $3, $4, $5)""",
            project_id,
            str(user_id),
            project_name,
            created_date,
            True,
        )
        
        # Создаем директорию для проекта (для совместимости со старым кодом)
        from utils.excel import create_user_dir
        user_dir = create_user_dir(user_id)
        project_dir = os.path.join(user_dir, "projects", str(project_id))
        if not os.path.exists(project_dir):
            os.makedirs(project_dir)
        
        return {
            'success': True,
            'project_id': project_id,
            'project_name': project_name,
            'message': f"Проект '{project_name}' создан"
        }
    
    try:
        return db.run_async(_do())
    except Exception as e:
        print(f"Ошибка при создании проекта: {e}")
        return {
            'success': False,
            'message': f"Ошибка при создании проекта: {e}"
        }

def get_all_projects(user_id):
    """
    Возвращает список всех проектов пользователя
    """
    async def _do():
        rows = await db.fetch(
            """SELECT project_id, project_name, created_date, is_active
               FROM projects
               WHERE user_id = $1 AND is_active = TRUE
               ORDER BY project_id""",
            str(user_id),
        )
        
        if not rows:
            return []
        
        # Конвертируем в список словарей
        result = []
        for row in rows:
            result.append({
                'project_id': row['project_id'],
                'project_name': row['project_name'],
                'created_date': row['created_date'].strftime('%Y-%m-%d') if row['created_date'] else None,
                'is_active': row['is_active'],
            })
        return result
    
    try:
        return db.run_async(_do())
    except Exception as e:
        print(f"Ошибка при получении списка проектов: {e}")
        return []

def get_project_by_id(user_id, project_id):
    """
    Возвращает проект по ID
    """
    async def _do():
        row = await db.fetchrow(
            """SELECT project_id, project_name, created_date, is_active
               FROM projects
               WHERE user_id = $1 AND project_id = $2 AND is_active = TRUE""",
            str(user_id),
            project_id,
        )
        
        if not row:
            return None
        
        return {
            'project_id': row['project_id'],
            'project_name': row['project_name'],
            'created_date': row['created_date'].strftime('%Y-%m-%d') if row['created_date'] else None,
            'is_active': row['is_active'],
        }
    
    try:
        return db.run_async(_do())
    except Exception as e:
        print(f"Ошибка при получении проекта по ID: {e}")
        return None

def get_project_by_name(user_id, project_name):
    """
    Возвращает проект по имени
    """
    async def _do():
        row = await db.fetchrow(
            """SELECT project_id, project_name, created_date, is_active
               FROM projects
               WHERE user_id = $1 AND LOWER(project_name) = LOWER($2) AND is_active = TRUE""",
            str(user_id),
            project_name,
        )
        
        if not row:
            return None
        
        return {
            'project_id': row['project_id'],
            'project_name': row['project_name'],
            'created_date': row['created_date'].strftime('%Y-%m-%d') if row['created_date'] else None,
            'is_active': row['is_active'],
        }
    
    try:
        return db.run_async(_do())
    except Exception as e:
        print(f"Ошибка при получении проекта по имени: {e}")
        return None

def delete_project(user_id, project_id):
    """
    Удаляет проект (помечает как неактивный и удаляет файлы)
    """
    async def _do():
        # Проверяем, существует ли проект
        project = await db.fetchrow(
            "SELECT project_name FROM projects WHERE user_id = $1 AND project_id = $2",
            str(user_id),
            project_id,
        )
        
        if not project:
            return {
                'success': False,
                'message': "Проект не найден"
            }
        
        project_name = project['project_name']
        
        # Помечаем проект как неактивный
        await db.execute(
            "UPDATE projects SET is_active = FALSE WHERE user_id = $1 AND project_id = $2",
            str(user_id),
            project_id,
        )
        
        # Если удаляемый проект был активным, сбрасываем активный проект
        await db.execute(
            "UPDATE users SET active_project_id = NULL WHERE user_id = $1 AND active_project_id = $2",
            str(user_id),
            project_id,
        )
        
        # Удаляем директорию проекта
        from utils.excel import create_user_dir
        user_dir = create_user_dir(user_id)
        project_dir = os.path.join(user_dir, "projects", str(project_id))
        if os.path.exists(project_dir):
            shutil.rmtree(project_dir)
        
        return {
            'success': True,
            'message': f"Проект '{project_name}' удален"
        }
    
    try:
        return db.run_async(_do())
    except Exception as e:
        print(f"Ошибка при удалении проекта: {e}")
        return {
            'success': False,
            'message': f"Ошибка при удалении проекта: {e}"
        }

def set_active_project(user_id, project_id):
    """
    Устанавливает активный проект
    """
    async def _do():
        # Убедимся, что пользователь существует
        await db.execute(
            "INSERT INTO users(user_id) VALUES($1) ON CONFLICT (user_id) DO NOTHING",
            str(user_id),
        )
        
        # Если project_id is None, переключаемся на общие расходы
        if project_id is None:
            await db.execute(
                "UPDATE users SET active_project_id = NULL WHERE user_id = $1",
                str(user_id),
            )
            
            return {
                'success': True,
                'project_id': None,
                'project_name': None,
                'message': "Переключено на общие расходы"
            }
        
        # Проверяем, существует ли проект
        project = await db.fetchrow(
            "SELECT project_name FROM projects WHERE user_id = $1 AND project_id = $2 AND is_active = TRUE",
            str(user_id),
            project_id,
        )
        
        if not project:
            return {
                'success': False,
                'message': "Проект не найден"
            }
        
        project_name = project['project_name']
        
        # Устанавливаем активный проект
        await db.execute(
            "UPDATE users SET active_project_id = $2 WHERE user_id = $1",
            str(user_id),
            project_id,
        )
        
        return {
            'success': True,
            'project_id': project_id,
            'project_name': project_name,
            'message': f"Переключено на проект '{project_name}'"
        }
    
    try:
        return db.run_async(_do())
    except Exception as e:
        print(f"Ошибка при установке активного проекта: {e}")
        return {
            'success': False,
            'message': f"Ошибка при установке активного проекта: {e}"
        }

def get_active_project(user_id):
    """
    Возвращает информацию об активном проекте
    """
    async def _do():
        # Получаем active_project_id из users
        user_row = await db.fetchrow(
            "SELECT active_project_id FROM users WHERE user_id = $1",
            str(user_id),
        )
        
        # Если пользователя нет или active_project_id не установлен
        if not user_row or user_row['active_project_id'] is None:
            return None
        
        active_project_id = user_row['active_project_id']
        
        # Получаем информацию о проекте
        project = await db.fetchrow(
            """SELECT project_id, project_name, created_date, is_active
               FROM projects
               WHERE user_id = $1 AND project_id = $2 AND is_active = TRUE""",
            str(user_id),
            active_project_id,
        )
        
        if not project:
            return None
        
        return {
            'project_id': project['project_id'],
            'project_name': project['project_name'],
            'created_date': project['created_date'].strftime('%Y-%m-%d') if project['created_date'] else None,
            'is_active': project['is_active'],
        }
    
    try:
        return db.run_async(_do())
    except Exception as e:
        print(f"Ошибка при получении активного проекта: {e}")
        return None

def get_project_stats(user_id, project_id, year=None):
    """
    Возвращает статистику по проекту
    """
    from utils.excel import get_all_expenses
    
    if year is None:
        year = datetime.datetime.now().year
    
    try:
        expenses_df = get_all_expenses(user_id, year, project_id)
        
        if expenses_df is None or expenses_df.empty:
            return {
                'total': 0,
                'count': 0,
                'by_category': {}
            }
        
        # Конвертируем amount в numeric, если необходимо
        if 'amount' in expenses_df.columns:
            expenses_df['amount'] = pd.to_numeric(expenses_df['amount'], errors='coerce')
        
        total = float(expenses_df['amount'].sum())
        count = len(expenses_df)
        by_category = expenses_df.groupby('category')['amount'].sum().to_dict()
        # Конвертируем значения в float
        by_category = {k: float(v) for k, v in by_category.items()}
        
        return {
            'total': total,
            'count': count,
            'by_category': by_category
        }
    except Exception as e:
        print(f"Ошибка при получении статистики проекта: {e}")
        return {
            'total': 0,
            'count': 0,
            'by_category': {}
        }
