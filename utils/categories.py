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
    Gets categories for user and project.
    Returns:
    - System categories (is_system = TRUE) first
    - User categories (is_system = FALSE) second
    - Only active categories (is_active = TRUE)
    - Global categories (project_id IS NULL) and project-specific categories
    
    For shared projects: returns categories created by ANY project member.
    For personal: returns only user's own global categories.
    
    Permission required: VIEW_STATS (owner, editor, or viewer for projects)
    
    Args:
        user_id: User ID (for access validation)
        project_id: Project ID (None for global categories)
    
    Returns:
        List of category dictionaries
    """
    try:
        # Validate permission if project_id is specified
        if project_id is not None:
            from utils.permissions import Permission, has_permission
            if not await has_permission(user_id, project_id, Permission.VIEW_STATS):
                log_error(logger, Exception("Permission denied"), 
                         "get_categories_permission_denied", user_id=user_id, project_id=project_id)
                return []
        
        # For projects: get categories from ALL project members
        # For personal: get only user's own global categories
        if project_id is not None:
            rows = await db.fetch(
                """
                WITH deduplicated AS (
                    SELECT DISTINCT ON (LOWER(c.name))
                           c.category_id, c.name, c.is_system, c.is_active,
                           c.project_id, c.created_at, c.user_id
                    FROM categories c
                    WHERE c.is_active = TRUE
                      AND (
                        c.project_id = $1
                        OR (c.project_id IS NULL AND c.user_id = (
                            SELECT user_id FROM projects WHERE project_id = $1
                        ))
                      )
                    ORDER BY LOWER(c.name),
                             CASE WHEN c.project_id = $1 THEN 0 ELSE 1 END,
                             c.is_system DESC
                )
                SELECT * FROM deduplicated
                ORDER BY is_system DESC, name ASC
                """,
                project_id
            )
        else:
            rows = await db.fetch(
                """
                SELECT category_id, name, is_system, is_active, project_id, created_at, user_id
                FROM categories
                WHERE user_id = $1
                  AND is_active = TRUE
                  AND project_id IS NULL
                ORDER BY is_system DESC, name ASC
                """,
                str(user_id)
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
    Получает категорию по ID с проверкой доступа.
    
    For shared projects: returns category if user is a project member.
    For personal: returns category if it belongs to the user.
    
    Args:
        user_id: ID пользователя
        category_id: ID категории
    
    Returns:
        Словарь с информацией о категории или None
    """
    try:
        row = await db.fetchrow(
            """
            SELECT c.category_id, c.name, c.is_system, c.is_active, c.project_id, c.created_at
            FROM categories c
            WHERE c.category_id = $1
              AND c.is_active = TRUE
              AND (
                  c.user_id = $2  -- User owns the category
                  OR c.project_id IS NULL  -- Global category (accessible to all)
                  OR EXISTS (
                      -- User is a member of the category's project
                      SELECT 1 FROM projects p
                      LEFT JOIN project_members pm ON p.project_id = pm.project_id AND pm.user_id = $2
                      WHERE p.project_id = c.project_id
                        AND p.is_active = TRUE
                        AND (p.user_id = $2 OR pm.user_id = $2)
                  )
              )
            """,
            category_id,
            str(user_id)
        )
        
        if not row:
            log_event(logger, "get_category_by_id_not_found", 
                     user_id=user_id, category_id=category_id)
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


async def get_category_by_id_only(category_id: int) -> Optional[Dict]:
    """
    Получает категорию по ID без проверки владельца.
    Используется для shared проектов, где категория может принадлежать другому участнику.
    Разрешение уже проверено на уровне проекта.

    Args:
        category_id: ID категории

    Returns:
        Словарь с информацией о категории или None
    """
    try:
        row = await db.fetchrow(
            """
            SELECT category_id, name, is_system, is_active, project_id, created_at
            FROM categories
            WHERE category_id = $1 AND is_active = TRUE
            """,
            category_id
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
        log_error(logger, e, "get_category_by_id_only_error", category_id=category_id)
        return None


async def create_category(
    user_id: int,
    name: str,
    project_id: Optional[int] = None,
    is_system: bool = False
) -> Dict:
    """
    Создает новую категорию для пользователя.
    
    Permission required: ADD_CATEGORY (owner or editor for projects)
    
    Args:
        user_id: ID пользователя
        name: Название категории
        project_id: ID проекта (None для глобальной категории)
        is_system: Является ли категория системной
    
    Returns:
        Словарь с результатом операции
    """
    try:
        # Check permission for project categories
        if project_id is not None:
            from utils.permissions import Permission, has_permission
            if not await has_permission(user_id, project_id, Permission.ADD_CATEGORY):
                return {
                    'success': False,
                    'message': "У вас нет прав на создание категорий в этом проекте"
                }
        # Убеждаемся, что пользователь существует
        await db.execute(
            "INSERT INTO users(user_id) VALUES($1) ON CONFLICT (user_id) DO NOTHING",
            str(user_id)
        )
        
        # Проверяем на дубликат среди активных категорий (case-insensitive)
        existing_active = await db.fetchrow(
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
        
        if existing_active:
            return {
                'success': False,
                'message': f"Категория '{name}' уже существует в этом проекте"
            }
        
        # Проверяем, есть ли неактивная категория с таким же именем
        existing_inactive = await db.fetchrow(
            """
            SELECT category_id FROM categories
            WHERE user_id = $1
              AND ((project_id IS NULL AND $2::int IS NULL) OR project_id = $2)
              AND LOWER(name) = LOWER($3)
              AND is_active = FALSE
            """,
            str(user_id),
            project_id,
            name.strip()
        )
        
        if existing_inactive:
            # Реактивируем существующую категорию
            category_id = existing_inactive['category_id']
            await db.execute(
                """
                UPDATE categories
                SET is_active = TRUE, is_system = $1
                WHERE category_id = $2 AND user_id = $3
                """,
                is_system,
                category_id,
                str(user_id)
            )
            
            log_event(logger, "create_category_reactivated", user_id=user_id,
                     category_id=category_id, category_name=name, project_id=project_id, is_system=is_system)
            
            return {
                'success': True,
                'category_id': category_id,
                'name': name.strip(),
                'project_id': project_id,
                'message': f"Категория '{name}' восстановлена"
            }
        
        # Создаем новую категорию
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


async def delete_category_with_transfer(user_id: int, category_id: int, target_category_id: int) -> Dict:
    """
    Deletes a category and transfers all expenses to another category.
    For shared projects: transfers ALL expenses from all members.
    For personal: transfers only user's expenses.
    
    Permission required: DELETE_CATEGORY (owner or editor for projects)
    
    Args:
        user_id: User ID (must own the category to delete it)
        category_id: ID of category to delete
        target_category_id: ID of category to transfer expenses to
    
    Returns:
        Dictionary with operation result
    """
    try:
        # Check that category belongs to user
        category = await get_category_by_id(user_id, category_id)
        if not category:
            return {
                'success': False,
                'message': "Категория не найдена"
            }
        
        # Check permission for project categories
        if category['project_id'] is not None:
            from utils.permissions import Permission, has_permission
            if not await has_permission(user_id, category['project_id'], Permission.DELETE_CATEGORY):
                return {
                    'success': False,
                    'message': "У вас нет прав на удаление категорий в этом проекте"
                }
        
        # Check target category exists and user has access
        target_category = await get_category_by_id(user_id, target_category_id)
        if not target_category:
            return {
                'success': False,
                'message': "Целевая категория не найдена"
            }
        
        from utils import db
        
        # Get count of expenses to transfer
        # For project categories: count ALL members' expenses
        # For personal: count only user's expenses
        if category['project_id'] is not None:
            transferred_count = await db.fetchval(
                """
                SELECT COUNT(*) FROM expenses
                WHERE category_id = $1 AND project_id = $2
                """,
                category_id,
                category['project_id']
            )
        else:
            transferred_count = await db.fetchval(
                """
                SELECT COUNT(*) FROM expenses
                WHERE category_id = $1 AND user_id = $2 AND project_id IS NULL
                """,
                category_id,
                str(user_id)
            )
        
        if transferred_count is None:
            transferred_count = 0
        
        # Transfer expenses
        if transferred_count > 0:
            if category['project_id'] is not None:
                await db.execute(
                    """
                    UPDATE expenses
                    SET category_id = $1
                    WHERE category_id = $2 AND project_id = $3
                    """,
                    target_category_id,
                    category_id,
                    category['project_id']
                )
            else:
                await db.execute(
                    """
                    UPDATE expenses
                    SET category_id = $1
                    WHERE category_id = $2 AND user_id = $3 AND project_id IS NULL
                    """,
                    target_category_id,
                    category_id,
                    str(user_id)
                )
        
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
        
        log_event(logger, "delete_category_with_transfer_success", user_id=user_id,
                 category_id=category_id, target_category_id=target_category_id,
                 transferred_count=transferred_count)
        
        return {
            'success': True,
            'message': f"Категория '{category['name']}' удалена. {transferred_count} расходов перенесено в '{target_category['name']}'.",
            'transferred_count': transferred_count
        }
        
    except Exception as e:
        log_error(logger, e, "delete_category_with_transfer_error", user_id=user_id,
                 category_id=category_id, target_category_id=target_category_id)
        return {
            'success': False,
            'message': f"Ошибка при удалении категории: {str(e)}"
        }


async def deactivate_category(user_id: int, category_id: int) -> Dict:
    """
    Deactivates a category (soft delete).
    Does not allow deactivation if the category is used in expenses.
    For shared projects: checks if ANY member is using the category.
    
    Permission required: DELETE_CATEGORY (owner or editor for projects)
    
    Args:
        user_id: User ID (must own the category to deactivate it)
        category_id: Category ID
    
    Returns:
        Dictionary with operation result
    """
    try:
        # Check that category belongs to user
        category = await get_category_by_id(user_id, category_id)
        if not category:
            return {
                'success': False,
                'message': "Категория не найдена"
            }
        
        # Check permission for project categories
        if category['project_id'] is not None:
            from utils.permissions import Permission, has_permission
            if not await has_permission(user_id, category['project_id'], Permission.DELETE_CATEGORY):
                return {
                    'success': False,
                    'message': "У вас нет прав на удаление категорий в этом проекте"
                }
        
        # Check if category is used in expenses
        # For project categories: check ALL members' expenses
        # For personal: check only user's expenses
        if category['project_id'] is not None:
            usage_count = await db.fetchval(
                """
                SELECT COUNT(*) FROM expenses
                WHERE category_id = $1 AND project_id = $2
                """,
                category_id,
                category['project_id']
            )
        else:
            usage_count = await db.fetchval(
                """
                SELECT COUNT(*) FROM expenses
                WHERE category_id = $1 AND user_id = $2 AND project_id IS NULL
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
