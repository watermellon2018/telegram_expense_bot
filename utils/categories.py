"""
Утилиты для работы с категориями расходов.
Поддерживает пользовательские и системные категории, глобальные и привязанные к проектам.
"""

import datetime
from typing import Optional, List, Dict
from . import db
from utils.logger import get_logger, log_event, log_error

logger = get_logger("utils.categories")


async def get_categories_for_user_project(user_id: int, project_id: Optional[int] = None) -> List[Dict]:
    """
    Получает список категорий для пользователя и проекта.
    Возвращает:
    - Системные категории (is_system = TRUE) сначала
    - Пользовательские категории (is_system = FALSE) потом
    - Только активные категории (is_active = TRUE)
    - Глобальные категории (project_id IS NULL) и категории проекта
    
    Args:
        user_id: ID пользователя
        project_id: ID проекта (None для глобальных категорий)
    
    Returns:
        Список словарей с информацией о категориях
    """
    try:
        rows = await db.fetch(
            """
            SELECT category_id, name, is_system, is_active, project_id, created_at
            FROM categories
            WHERE user_id = $1
              AND is_active = TRUE
              AND (project_id = $2 OR project_id IS NULL)
            ORDER BY is_system DESC, name ASC
            """,
            str(user_id),
            project_id
        )
        
        categories = [
            {
                'category_id': r['category_id'],
                'name': r['name'],
                'is_system': r['is_system'],
                'is_active': r['is_active'],
                'project_id': r['project_id'],
                'created_at': r['created_at'].isoformat() if r['created_at'] else None
            }
            for r in rows
        ]
        
        log_event(logger, "get_categories_success", user_id=user_id, 
                 project_id=project_id, count=len(categories))
        return categories
        
    except Exception as e:
        log_error(logger, e, "get_categories_error", user_id=user_id, project_id=project_id)
        return []


async def get_category_by_id(user_id: int, category_id: int) -> Optional[Dict]:
    """
    Получает категорию по ID с проверкой принадлежности пользователю.
    
    Args:
        user_id: ID пользователя
        category_id: ID категории
    
    Returns:
        Словарь с информацией о категории или None
    """
    try:
        row = await db.fetchrow(
            """
            SELECT category_id, name, is_system, is_active, project_id, created_at
            FROM categories
            WHERE category_id = $1 AND user_id = $2
            """,
            category_id,
            str(user_id)
        )
        
        if not row:
            return None
        
        return {
            'category_id': row['category_id'],
            'name': row['name'],
            'is_system': row['is_system'],
            'is_active': row['is_active'],
            'project_id': row['project_id'],
            'created_at': row['created_at'].isoformat() if row['created_at'] else None
        }
    except Exception as e:
        log_error(logger, e, "get_category_by_id_error", user_id=user_id, category_id=category_id)
        return None


async def create_category(
    user_id: int, 
    name: str, 
    project_id: Optional[int] = None,
    is_system: bool = False
) -> Dict:
    """
    Создает новую категорию для пользователя.
    
    Args:
        user_id: ID пользователя
        name: Название категории
        project_id: ID проекта (None для глобальной категории)
        is_system: Является ли категория системной
    
    Returns:
        Словарь с результатом операции
    """
    try:
        # Убеждаемся, что пользователь существует
        await db.execute(
            "INSERT INTO users(user_id) VALUES($1) ON CONFLICT (user_id) DO NOTHING",
            str(user_id)
        )
        
        # Проверяем на дубликат (case-insensitive)
        existing = await db.fetchrow(
            """
            SELECT category_id FROM categories
            WHERE user_id = $1
              AND ((project_id IS NULL AND $2::int IS NULL) OR project_id = $2)
              AND LOWER(name) = LOWER($3)
              AND is_active = TRUE
            """,
            str(user_id),
            project_id,
            name.strip()
        )
        
        if existing:
            return {
                'success': False,
                'message': f"Категория '{name}' уже существует в этом проекте"
            }
        
        # Создаем категорию
        category_id = await db.fetchval(
            """
            INSERT INTO categories(user_id, project_id, name, is_system, is_active, created_at)
            VALUES($1, $2, $3, $4, TRUE, CURRENT_TIMESTAMP)
            RETURNING category_id
            """,
            str(user_id),
            project_id,
            name.strip(),
            is_system
        )
        
        log_event(logger, "create_category_success", user_id=user_id,
                 category_id=category_id, category_name=name, project_id=project_id, is_system=is_system)
        
        return {
            'success': True,
            'category_id': category_id,
            'name': name.strip(),
            'project_id': project_id,
            'message': f"Категория '{name}' создана"
        }
        
    except Exception as e:
        log_error(logger, e, "create_category_error", user_id=user_id, category_name=name, project_id=project_id)
        return {
            'success': False,
            'message': f"Ошибка при создании категории: {str(e)}"
        }


async def deactivate_category(user_id: int, category_id: int) -> Dict:
    """
    Деактивирует категорию (soft delete).
    Не позволяет деактивировать категории, которые используются в расходах.
    
    Args:
        user_id: ID пользователя
        category_id: ID категории
    
    Returns:
        Словарь с результатом операции
    """
    try:
        # Проверяем, что категория принадлежит пользователю
        category = await get_category_by_id(user_id, category_id)
        if not category:
            return {
                'success': False,
                'message': "Категория не найдена"
            }
        
        # Проверяем, используется ли категория в расходах
        usage_count = await db.fetchval(
            """
            SELECT COUNT(*) FROM expenses
            WHERE category_id = $1 AND user_id = $2
            """,
            category_id,
            str(user_id)
        )
        
        if usage_count > 0:
            return {
                'success': False,
                'message': f"Категория используется в {usage_count} расходах. Удаление невозможно."
            }
        
        # Деактивируем категорию
        await db.execute(
            """
            UPDATE categories
            SET is_active = FALSE
            WHERE category_id = $1 AND user_id = $2
            """,
            category_id,
            str(user_id)
        )
        
        log_event(logger, "deactivate_category_success", user_id=user_id, category_id=category_id)
        
        return {
            'success': True,
            'message': f"Категория '{category['name']}' деактивирована"
        }
        
    except Exception as e:
        log_error(logger, e, "deactivate_category_error", user_id=user_id, category_id=category_id)
        return {
            'success': False,
            'message': f"Ошибка при деактивации категории: {str(e)}"
        }


async def ensure_system_categories_exist(user_id: int) -> None:
    """
    Убеждается, что у пользователя есть все системные категории.
    Вызывается при первом использовании бота.
    
    Args:
        user_id: ID пользователя
    """
    import config
    
    try:
        await db.execute(
            "INSERT INTO users(user_id) VALUES($1) ON CONFLICT (user_id) DO NOTHING",
            str(user_id)
        )
        
        for category_name in config.DEFAULT_CATEGORIES.keys():
            await create_category(
                user_id=user_id,
                name=category_name,
                project_id=None,
                is_system=True
            )
        
        log_event(logger, "ensure_system_categories_success", user_id=user_id)
        
    except Exception as e:
        log_error(logger, e, "ensure_system_categories_error", user_id=user_id)


async def get_category_name_by_id(user_id: int, category_id: int) -> Optional[str]:
    """
    Получает название категории по ID (для обратной совместимости).
    
    Args:
        user_id: ID пользователя
        category_id: ID категории
    
    Returns:
        Название категории или None
    """
    category = await get_category_by_id(user_id, category_id)
    return category['name'] if category else None
