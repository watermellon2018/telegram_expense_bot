"""
Role-based access control for shared projects.
Defines permissions for different user roles in projects.
"""

from typing import Optional
from enum import Enum
from . import projects
from utils.logger import get_logger, log_event, log_error

logger = get_logger("utils.permissions")


class Permission(Enum):
    """Permission types for project operations"""
    # Project management
    DELETE_PROJECT = "delete_project"
    INVITE_MEMBERS = "invite_members"
    REMOVE_MEMBERS = "remove_members"
    CHANGE_ROLES = "change_roles"
    
    # Expense operations
    ADD_EXPENSE = "add_expense"
    EDIT_EXPENSE = "edit_expense"
    DELETE_EXPENSE = "delete_expense"
    
    # Category operations
    ADD_CATEGORY = "add_category"
    EDIT_CATEGORY = "edit_category"
    DELETE_CATEGORY = "delete_category"
    
    # View operations
    VIEW_STATS = "view_stats"
    VIEW_HISTORY = "view_history"
    VIEW_MEMBERS = "view_members"
    
    # Budget operations
    SET_BUDGET = "set_budget"
    VIEW_BUDGET = "view_budget"


# Role permissions mapping
ROLE_PERMISSIONS = {
    'owner': {
        # Owners can do everything
        Permission.DELETE_PROJECT,
        Permission.INVITE_MEMBERS,
        Permission.REMOVE_MEMBERS,
        Permission.CHANGE_ROLES,
        Permission.ADD_EXPENSE,
        Permission.EDIT_EXPENSE,
        Permission.DELETE_EXPENSE,
        Permission.ADD_CATEGORY,
        Permission.EDIT_CATEGORY,
        Permission.DELETE_CATEGORY,
        Permission.VIEW_STATS,
        Permission.VIEW_HISTORY,
        Permission.VIEW_MEMBERS,
        Permission.SET_BUDGET,
        Permission.VIEW_BUDGET,
    },
    'editor': {
        # Editors can modify data but not manage the project
        Permission.ADD_EXPENSE,
        Permission.EDIT_EXPENSE,
        Permission.DELETE_EXPENSE,
        Permission.ADD_CATEGORY,
        Permission.EDIT_CATEGORY,
        Permission.DELETE_CATEGORY,
        Permission.VIEW_STATS,
        Permission.VIEW_HISTORY,
        Permission.VIEW_MEMBERS,
        Permission.SET_BUDGET,
        Permission.VIEW_BUDGET,
    },
    'viewer': {
        # Viewers can only read data
        Permission.VIEW_STATS,
        Permission.VIEW_HISTORY,
        Permission.VIEW_MEMBERS,
        Permission.VIEW_BUDGET,
    }
}


async def has_permission(
    user_id: int,
    project_id: Optional[int],
    permission: Permission
) -> bool:
    """
    Check if user has a specific permission in a project.
    
    Args:
        user_id: User ID to check
        project_id: Project ID (None for personal operations)
        permission: Permission to check
    
    Returns:
        True if user has permission, False otherwise
    """
    # Personal operations (project_id=None) always allowed for the user
    if project_id is None:
        return True
    
    try:
        # Get user's role in the project
        role = await projects.get_user_role_in_project(user_id, project_id)
        
        log_event(logger, "permission_check_debug",
                 user_id=user_id, project_id=project_id,
                 role=role, permission=permission.value)
        
        if role is None:
            log_event(logger, "permission_denied_not_member", 
                     user_id=user_id, project_id=project_id, 
                     permission=permission.value)
            return False
        
        # Check if role has the permission
        role_perms = ROLE_PERMISSIONS.get(role, set())
        has_perm = permission in role_perms
        
        log_event(logger, "permission_check_result",
                 user_id=user_id, project_id=project_id,
                 role=role, permission=permission.value,
                 has_permission=has_perm,
                 role_permissions=[p.value for p in role_perms])
        
        if not has_perm:
            log_event(logger, "permission_denied_insufficient_role",
                     user_id=user_id, project_id=project_id,
                     role=role, permission=permission.value)
        else:
            log_event(logger, "permission_granted",
                     user_id=user_id, project_id=project_id,
                     role=role, permission=permission.value)
        
        return has_perm
        
    except Exception as e:
        log_error(logger, e, "permission_check_error",
                 user_id=user_id, project_id=project_id,
                 permission=permission.value)
        return False


async def require_permission(
    user_id: int,
    project_id: Optional[int],
    permission: Permission
) -> None:
    """
    Require that user has a specific permission, raise exception if not.
    
    Args:
        user_id: User ID to check
        project_id: Project ID
        permission: Required permission
    
    Raises:
        PermissionError: If user doesn't have the permission
    """
    if not await has_permission(user_id, project_id, permission):
        role = await projects.get_user_role_in_project(user_id, project_id) if project_id else None
        raise PermissionError(
            f"User {user_id} with role '{role}' does not have permission '{permission.value}' "
            f"for project {project_id}"
        )


async def get_user_permissions(
    user_id: int,
    project_id: Optional[int]
) -> set[Permission]:
    """
    Get all permissions for a user in a project.
    
    Args:
        user_id: User ID
        project_id: Project ID (None for personal)
    
    Returns:
        Set of permissions user has
    """
    if project_id is None:
        # For personal operations, user has all permissions
        return ROLE_PERMISSIONS['owner']
    
    try:
        role = await projects.get_user_role_in_project(user_id, project_id)
        if role is None:
            return set()
        
        return ROLE_PERMISSIONS.get(role, set())
    except Exception as e:
        log_error(logger, e, "get_permissions_error",
                 user_id=user_id, project_id=project_id)
        return set()


async def can_modify_expense(
    user_id: int,
    expense_user_id: str,
    project_id: Optional[int]
) -> bool:
    """
    Check if user can edit/delete a specific expense.
    Users can always modify their own expenses.
    Editors/owners can modify any expense in the project.
    
    Args:
        user_id: User attempting the modification
        expense_user_id: User who created the expense
        project_id: Project ID
    
    Returns:
        True if user can modify the expense
    """
    # User can always modify their own expenses
    if str(user_id) == expense_user_id:
        return True
    
    # For personal expenses, only owner can modify
    if project_id is None:
        return False
    
    # For project expenses, check role permissions
    return await has_permission(user_id, project_id, Permission.EDIT_EXPENSE)


def get_permission_description(permission: Permission) -> str:
    """Get human-readable description of a permission"""
    descriptions = {
        Permission.DELETE_PROJECT: "Удалить проект",
        Permission.INVITE_MEMBERS: "Приглашать участников",
        Permission.REMOVE_MEMBERS: "Удалять участников",
        Permission.CHANGE_ROLES: "Изменять роли",
        Permission.ADD_EXPENSE: "Добавлять расходы",
        Permission.EDIT_EXPENSE: "Редактировать расходы",
        Permission.DELETE_EXPENSE: "Удалять расходы",
        Permission.ADD_CATEGORY: "Создавать категории",
        Permission.EDIT_CATEGORY: "Редактировать категории",
        Permission.DELETE_CATEGORY: "Удалять категории",
        Permission.VIEW_STATS: "Просматривать статистику",
        Permission.VIEW_HISTORY: "Просматривать историю",
        Permission.VIEW_MEMBERS: "Просматривать участников",
        Permission.SET_BUDGET: "Устанавливать бюджет",
        Permission.VIEW_BUDGET: "Просматривать бюджет",
    }
    return descriptions.get(permission, permission.value)


def get_role_description(role: str) -> str:
    """Get human-readable description of a role"""
    descriptions = {
        'owner': '👑 Владелец',
        'editor': '✏️ Редактор',
        'viewer': '👁️ Наблюдатель',
    }
    return descriptions.get(role, role)


def get_role_permissions_list(role: str) -> list[str]:
    """Get list of permission descriptions for a role"""
    permissions = ROLE_PERMISSIONS.get(role, set())
    return [get_permission_description(p) for p in permissions]
