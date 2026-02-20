"""
Утилиты для работы с проектами
Теперь все данные хранятся в Postgres вместо Excel.
"""

import os
import datetime
import pandas as pd
import secrets
import config
from typing import Optional, Dict
from . import db
from utils.logger import get_logger, log_event, log_error

from telegram import Update
from telegram.ext import ContextTypes

logger = get_logger("utils.projects")

async def cmd_create_project(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if not context.args:
        await update.message.reply_text("Использование: /newproject Название проекта")
        return
    
    project_name = " ".join(context.args)
    
    result = await create_project(user_id, project_name)
    
    if result['success']:
        await update.message.reply_text(f"Проект создан!\nID: {result['project_id']}\nНазвание: {result['project_name']}")
    else:
        await update.message.reply_text(result['message'])



async def create_project(user_id: int, project_name: str) -> dict:
    """
    Create a new project. The creator becomes the owner.
    Owner is added to project_members for consistency (optional but recommended).
    """
    await db.execute(
        "INSERT INTO users(user_id) VALUES($1) ON CONFLICT (user_id) DO NOTHING",
        str(user_id),
    )
    
    # Check for duplicate in projects user has access to
    existing = await db.fetchrow(
        """
        SELECT p.project_id 
        FROM projects p
        LEFT JOIN project_members pm ON p.project_id = pm.project_id AND pm.user_id = $1
        WHERE LOWER(p.project_name) = LOWER($2) AND p.is_active = TRUE
          AND (p.user_id = $1 OR pm.user_id = $1)
        """,
        str(user_id), project_name
    )
    if existing:
        return {'success': False, 'message': f"Проект '{project_name}' уже существует"}
    
    # Insert project and let database generate project_id from sequence
    row = await db.fetchrow(
        """INSERT INTO projects(user_id, project_name, created_date, is_active)
           VALUES($1, $2, $3, $4)
           RETURNING project_id""",
        str(user_id), project_name, datetime.date.today(), True
    )
    project_id = row['project_id']
    
    # Optionally add owner to project_members for consistency
    # This makes queries simpler since you can always check project_members
    await db.execute(
        """INSERT INTO project_members(project_id, user_id, role, joined_at)
           VALUES($1, $2, 'owner', NOW())
           ON CONFLICT (project_id, user_id) DO NOTHING""",
        project_id, str(user_id)
    )
    
    # Create directory (if still needed for compatibility)
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
    """
    Get all projects the user has access to (owned or member of)
    """
    rows = await db.fetch(
        """
        SELECT DISTINCT p.project_id, p.project_name, p.created_date, p.is_active,
               p.user_id as owner_id,
               COALESCE(pm.role, 'owner') as role
        FROM projects p
        LEFT JOIN project_members pm ON p.project_id = pm.project_id AND pm.user_id = $1
        WHERE p.is_active = TRUE
          AND (p.user_id = $1 OR pm.user_id = $1)
        ORDER BY p.project_id
        """,
        str(user_id)
    )
    
    return [
        {
            'project_id': r['project_id'],
            'project_name': r['project_name'],
            'created_date': r['created_date'].strftime('%Y-%m-%d') if r['created_date'] else None,
            'is_active': r['is_active'],
            'owner_id': r['owner_id'],
            'role': r['role'],
            'is_owner': r['owner_id'] == str(user_id),
        }
        for r in rows
    ]


async def get_project_by_id(user_id: int, project_id: int) -> Optional[dict]:
    """
    Get project by ID, checking if user has access (owner or member)
    """
    row = await db.fetchrow(
        """
        SELECT DISTINCT p.project_id, p.project_name, p.created_date, p.is_active,
               p.user_id as owner_id,
               COALESCE(pm.role, 'owner') as role
        FROM projects p
        LEFT JOIN project_members pm ON p.project_id = pm.project_id AND pm.user_id = $1
        WHERE p.project_id = $2 AND p.is_active = TRUE
          AND (p.user_id = $1 OR pm.user_id = $1)
        """,
        str(user_id), project_id
    )
    if not row:
        return None
    
    return {
        'project_id': row['project_id'],
        'project_name': row['project_name'],
        'created_date': row['created_date'].strftime('%Y-%m-%d') if row['created_date'] else None,
        'is_active': row['is_active'],
        'owner_id': row['owner_id'],
        'role': row['role'],
        'is_owner': row['owner_id'] == str(user_id),
    }

async def get_project_by_name(user_id: int, project_name: str) -> Optional[dict]:
    """
    Get project by name, checking if user has access (owner or member)
    """
    row = await db.fetchrow(
        """
        SELECT DISTINCT p.project_id, p.project_name, p.created_date, p.is_active,
               p.user_id as owner_id,
               COALESCE(pm.role, 'owner') as role
        FROM projects p
        LEFT JOIN project_members pm ON p.project_id = pm.project_id AND pm.user_id = $1
        WHERE LOWER(p.project_name) = LOWER($2) AND p.is_active = TRUE
          AND (p.user_id = $1 OR pm.user_id = $1)
        """,
        str(user_id), project_name
    )
    if not row:
        return None
    
    return {
        'project_id': row['project_id'],
        'project_name': row['project_name'],
        'created_date': row['created_date'].strftime('%Y-%m-%d') if row['created_date'] else None,
        'is_active': row['is_active'],
        'owner_id': row['owner_id'],
        'role': row['role'],
        'is_owner': row['owner_id'] == str(user_id),
    }


async def is_project_member(user_id: int, project_id: int) -> bool:
    """
    Check if user has access to project (owner or member)
    """
    row = await db.fetchrow(
        """
        SELECT 1
        FROM projects p
        LEFT JOIN project_members pm ON p.project_id = pm.project_id AND pm.user_id = $1
        WHERE p.project_id = $2 AND p.is_active = TRUE
          AND (p.user_id = $1 OR pm.user_id = $1)
        """,
        str(user_id), project_id
    )
    return row is not None


async def get_user_role_in_project(user_id: int, project_id: int) -> Optional[str]:
    """
    Get user's role in project. Returns 'owner', 'editor', 'viewer', or None if not a member
    """
    from utils.logger import log_event
    
    row = await db.fetchrow(
        """
        SELECT 
            p.user_id as owner_id,
            pm.user_id as member_id,
            pm.role as member_role,
            CASE 
                WHEN p.user_id = $1 THEN 'owner'
                WHEN pm.role IS NOT NULL THEN pm.role
                ELSE NULL 
            END as role
        FROM projects p
        LEFT JOIN project_members pm ON p.project_id = pm.project_id AND pm.user_id = $1
        WHERE p.project_id = $2 AND p.is_active = TRUE
        """,
        str(user_id), project_id
    )
    
    log_event(logger, "get_user_role_in_project_debug",
             user_id=user_id, project_id=project_id,
             row_found=row is not None,
             owner_id=row['owner_id'] if row else None,
             member_id=row['member_id'] if row else None,
             member_role=row['member_role'] if row else None,
             computed_role=row['role'] if row else None)
    
    return row['role'] if row else None


async def get_project_members(project_id: int) -> list:
    """
    Get all members of a project including the owner.
    The owner is stored in project_members with role='owner' (inserted on project creation).
    """
    rows = await db.fetch(
        """
        SELECT pm.user_id, pm.role, pm.joined_at
        FROM project_members pm
        WHERE pm.project_id = $1
        ORDER BY pm.role DESC, pm.joined_at ASC
        """,
        project_id
    )

    return [
        {
            'user_id': r['user_id'],
            'role': r['role'],
            'joined_at': r['joined_at'].isoformat() if r['joined_at'] else None,
        }
        for r in rows
    ]


async def set_active_project(user_id: int, project_id: Optional[int]) -> dict:
    """
    Set user's active project. Validates that user has access to the project.
    """
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
    
    # Check if user has access to the project (owner or member)
    project = await get_project_by_id(user_id, project_id)
    if not project:
        return {'success': False, 'message': "Проект не найден или у вас нет доступа"}
    
    await db.execute(
        "UPDATE users SET active_project_id = $2 WHERE user_id = $1",
        str(user_id), project_id
    )
    
    return {
        'success': True,
        'project_id': project_id,
        'project_name': project['project_name'],
        'role': project['role'],
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

async def get_project_stats(user_id: int, project_id: int) -> dict:
    """
    Get project statistics. Shows all expenses from all members, not just the requesting user.
    """
    # Verify user has access to project
    if not await is_project_member(user_id, project_id):
        return {'count': 0, 'total': 0.0}
    
    row = await db.fetchrow(
        """
        SELECT COUNT(*) as count, COALESCE(SUM(amount), 0) as total
        FROM expenses 
        WHERE project_id = $1
        """,
        project_id
    )
    return {
        'count': row['count'],
        'total': float(row['total'])
    }

async def delete_project(user_id: int, project_id: int) -> dict:
    """
    Delete a project. Only the owner can delete.
    This will cascade delete expenses, categories, and memberships.
    
    Permission required: DELETE_PROJECT (owner only)
    """
    from utils.permissions import Permission, has_permission
    
    # Check permission
    if not await has_permission(user_id, project_id, Permission.DELETE_PROJECT):
        return {'success': False, 'message': "Только владелец может удалить проект"}
    
    # Check if project exists and user has access
    project = await get_project_by_id(user_id, project_id)
    if not project:
        return {'success': False, 'message': "Проект не найден или у вас нет доступа"}
    
    # Delete expenses (from all members, not just owner)
    await db.execute(
        "DELETE FROM expenses WHERE project_id = $1",
        project_id
    )
    
    # Delete categories associated with this project
    await db.execute(
        "UPDATE categories SET is_active = FALSE WHERE project_id = $1",
        project_id
    )
    
    # Delete project members
    await db.execute(
        "DELETE FROM project_members WHERE project_id = $1",
        project_id
    )
    
    # Delete the project
    await db.execute(
        "DELETE FROM projects WHERE project_id = $1",
        project_id
    )
    
    # Reset active_project_id for all users who had this project active
    await db.execute(
        "UPDATE users SET active_project_id = NULL WHERE active_project_id = $1",
        project_id
    )
    
    return {'success': True, 'message': f"Проект '{project['project_name']}' удален"}


async def create_invitation(
    user_id: int,
    project_id: int,
    role: str = 'editor',
    expires_in_hours: int = 24
) -> Dict:
    """
    Create an invitation token for a project.
    Only project owner can create invitations.
    
    Args:
        user_id: User creating the invitation (must be owner)
        project_id: Project to invite to
        role: Role for the invited user ('editor' or 'viewer')
        expires_in_hours: Token expiration time in hours
    
    Returns:
        Dictionary with token and invitation details
    """
    try:
        # Check if user is the project owner
        project = await get_project_by_id(user_id, project_id)
        if not project:
            return {'success': False, 'message': "Проект не найден или у вас нет доступа"}
        
        if not project['is_owner']:
            return {'success': False, 'message': "Только владелец может приглашать участников"}
        
        # Validate role
        if role not in ['editor', 'viewer']:
            return {'success': False, 'message': "Неверная роль. Используйте 'editor' или 'viewer'"}
        
        # Generate unique token
        token = secrets.token_urlsafe(32)
        
        # Calculate expiration time
        expires_at = datetime.datetime.now() + datetime.timedelta(hours=expires_in_hours)
        
        # Store invitation in database
        await db.execute(
            """
            INSERT INTO project_invites(token, project_id, inviter_id, role, created_at, expires_at)
            VALUES($1, $2, $3, $4, NOW(), $5)
            """,
            token,
            project_id,
            str(user_id),
            role,
            expires_at
        )
        
        log_event(logger, "invitation_created", user_id=user_id,
                 project_id=project_id, role=role, token_preview=token[:8])
        
        return {
            'success': True,
            'token': token,
            'project_id': project_id,
            'project_name': project['project_name'],
            'role': role,
            'expires_at': expires_at.isoformat(),
            'message': f"Приглашение создано для роли '{role}'"
        }
        
    except Exception as e:
        log_error(logger, e, "create_invitation_error",
                 user_id=user_id, project_id=project_id, role=role)
        return {'success': False, 'message': f"Ошибка при создании приглашения: {str(e)}"}


async def get_invitation_link(token: str, bot_username: str) -> str:
    """
    Generate invitation link for Telegram.
    
    Args:
        token: Invitation token
        bot_username: Bot's username (without @)
    
    Returns:
        Telegram deep link
    """
    return f"https://t.me/{bot_username}?start=inv_{token}"


async def accept_invitation(user_id: int, token: str) -> Dict:
    """
    Accept a project invitation using a token.
    Adds user to project_members and sets project as active.
    
    Args:
        user_id: User accepting the invitation
        token: Invitation token
    
    Returns:
        Dictionary with result
    """
    try:
        # Get invitation details
        invitation = await db.fetchrow(
            """
            SELECT i.*, p.project_name, p.user_id as owner_id
            FROM project_invites i
            JOIN projects p ON i.project_id = p.project_id
            WHERE i.token = $1
            """,
            token
        )
        
        if not invitation:
            log_event(logger, "invitation_not_found", user_id=user_id,
                     token_preview=token[:8] if token else "empty")
            return {'success': False, 'message': "Приглашение не найдено"}
        
        # Check if invitation has expired
        if invitation['expires_at'] < datetime.datetime.now():
            # Clean up expired invitation
            await db.execute(
                "DELETE FROM project_invites WHERE token = $1",
                token
            )
            log_event(logger, "invitation_expired", user_id=user_id,
                     project_id=invitation['project_id'],
                     token_preview=token[:8])
            return {'success': False, 'message': "Приглашение истекло"}
        
        # Check if user is already a member or owner
        existing_role = await get_user_role_in_project(user_id, invitation['project_id'])
        if existing_role:
            log_event(logger, "invitation_already_member", user_id=user_id,
                     project_id=invitation['project_id'], existing_role=existing_role)
            return {
                'success': False,
                'message': f"Вы уже участник проекта '{invitation['project_name']}' с ролью '{existing_role}'"
            }
        
        # Ensure user exists in users table
        await db.execute(
            "INSERT INTO users(user_id) VALUES($1) ON CONFLICT (user_id) DO NOTHING",
            str(user_id)
        )
        
        # Add user to project_members
        await db.execute(
            """
            INSERT INTO project_members(project_id, user_id, role, joined_at)
            VALUES($1, $2, $3, NOW())
            """,
            invitation['project_id'],
            str(user_id),
            invitation['role']
        )
        
        # Set project as active for the user
        await db.execute(
            "UPDATE users SET active_project_id = $1 WHERE user_id = $2",
            invitation['project_id'],
            str(user_id)
        )
        
        # Delete the used invitation token
        await db.execute(
            "DELETE FROM project_invites WHERE token = $1",
            token
        )
        
        log_event(logger, "invitation_accepted", user_id=user_id,
                 project_id=invitation['project_id'],
                 role=invitation['role'],
                 inviter_id=invitation['inviter_id'])
        
        return {
            'success': True,
            'project_id': invitation['project_id'],
            'project_name': invitation['project_name'],
            'role': invitation['role'],
            'message': f"Вы добавлены в проект '{invitation['project_name']}' с ролью '{invitation['role']}'"
        }
        
    except Exception as e:
        log_error(logger, e, "accept_invitation_error",
                 user_id=user_id, token_preview=token[:8] if token else "empty")
        return {'success': False, 'message': f"Ошибка при принятии приглашения: {str(e)}"}


async def remove_member(
    owner_id: int,
    project_id: int,
    member_id: int
) -> Dict:
    """
    Remove a member from a project.
    Only project owner can remove members.
    Cannot remove the owner.
    
    Args:
        owner_id: User attempting to remove member (must be owner)
        project_id: Project ID
        member_id: User ID to remove
    
    Returns:
        Dictionary with result
    """
    try:
        # Check if requesting user is the owner
        project = await get_project_by_id(owner_id, project_id)
        if not project:
            return {'success': False, 'message': "Проект не найден или у вас нет доступа"}
        
        if not project['is_owner']:
            return {'success': False, 'message': "Только владелец может удалять участников"}
        
        # Check if trying to remove the owner
        if str(member_id) == project['owner_id']:
            return {'success': False, 'message': "Нельзя удалить владельца проекта"}
        
        # Check if member exists
        member_role = await get_user_role_in_project(member_id, project_id)
        if not member_role or member_role == 'owner':
            return {'success': False, 'message': "Участник не найден в этом проекте"}
        
        # Remove from project_members
        await db.execute(
            "DELETE FROM project_members WHERE project_id = $1 AND user_id = $2",
            project_id,
            str(member_id)
        )
        
        # Reset active_project_id if this was their active project
        await db.execute(
            "UPDATE users SET active_project_id = NULL WHERE user_id = $1 AND active_project_id = $2",
            str(member_id),
            project_id
        )
        
        log_event(logger, "member_removed", owner_id=owner_id,
                 project_id=project_id, member_id=member_id,
                 removed_role=member_role)
        
        return {
            'success': True,
            'message': f"Участник удален из проекта"
        }
        
    except Exception as e:
        log_error(logger, e, "remove_member_error",
                 owner_id=owner_id, project_id=project_id, member_id=member_id)
        return {'success': False, 'message': f"Ошибка при удалении участника: {str(e)}"}


async def change_member_role(
    owner_id: int,
    project_id: int,
    member_id: int,
    new_role: str
) -> Dict:
    """
    Change a member's role in a project.
    Only project owner can change roles.
    Cannot change owner's role.
    
    Args:
        owner_id: User attempting to change role (must be owner)
        project_id: Project ID
        member_id: User whose role to change
        new_role: New role ('editor' or 'viewer')
    
    Returns:
        Dictionary with result
    """
    try:
        # Check if requesting user is the owner
        project = await get_project_by_id(owner_id, project_id)
        if not project:
            return {'success': False, 'message': "Проект не найден или у вас нет доступа"}
        
        if not project['is_owner']:
            return {'success': False, 'message': "Только владелец может изменять роли"}
        
        # Validate new role
        if new_role not in ['editor', 'viewer']:
            return {'success': False, 'message': "Неверная роль. Используйте 'editor' или 'viewer'"}
        
        # Check if trying to change owner's role
        if str(member_id) == project['owner_id']:
            return {'success': False, 'message': "Нельзя изменить роль владельца"}
        
        # Check if member exists
        current_role = await get_user_role_in_project(member_id, project_id)
        if not current_role or current_role == 'owner':
            return {'success': False, 'message': "Участник не найден в этом проекте"}
        
        if current_role == new_role:
            return {'success': False, 'message': f"Участник уже имеет роль '{new_role}'"}
        
        # Update role
        await db.execute(
            "UPDATE project_members SET role = $1 WHERE project_id = $2 AND user_id = $3",
            new_role,
            project_id,
            str(member_id)
        )
        
        log_event(logger, "member_role_changed", owner_id=owner_id,
                 project_id=project_id, member_id=member_id,
                 old_role=current_role, new_role=new_role)
        
        return {
            'success': True,
            'message': f"Роль участника изменена с '{current_role}' на '{new_role}'"
        }
        
    except Exception as e:
        log_error(logger, e, "change_role_error",
                 owner_id=owner_id, project_id=project_id,
                 member_id=member_id, new_role=new_role)
        return {'success': False, 'message': f"Ошибка при изменении роли: {str(e)}"}


async def leave_project(user_id: int, project_id: int) -> Dict:
    """
    Allow a member to leave a project.
    Owner cannot leave (must transfer ownership or delete project first).
    
    Args:
        user_id: User ID leaving the project
        project_id: Project ID to leave
    
    Returns:
        Dictionary with result
    """
    try:
        # Check if user is a member
        project = await get_project_by_id(user_id, project_id)
        if not project:
            return {'success': False, 'message': "Проект не найден или у вас нет доступа"}
        
        # Owner cannot leave
        if project['is_owner']:
            return {
                'success': False,
                'message': "Владелец не может покинуть проект. Сначала передайте владение или удалите проект."
            }
        
        # Remove from project_members
        await db.execute(
            "DELETE FROM project_members WHERE project_id = $1 AND user_id = $2",
            project_id,
            str(user_id)
        )
        
        # Reset active_project_id if this was their active project
        await db.execute(
            "UPDATE users SET active_project_id = NULL WHERE user_id = $1 AND active_project_id = $2",
            str(user_id),
            project_id
        )
        
        log_event(logger, "user_left_project", user_id=user_id,
                 project_id=project_id, project_name=project['project_name'])
        
        return {
            'success': True,
            'message': f"Вы покинули проект '{project['project_name']}'"
        }
        
    except Exception as e:
        log_error(logger, e, "leave_project_error",
                 user_id=user_id, project_id=project_id)
        return {'success': False, 'message': f"Ошибка при выходе из проекта: {str(e)}"}


async def cleanup_expired_invitations() -> int:
    """
    Clean up expired invitation tokens.
    Should be called periodically (e.g., daily).
    
    Returns:
        Number of expired invitations deleted
    """
    try:
        result = await db.execute(
            "DELETE FROM project_invites WHERE expires_at < NOW()"
        )
        # Extract number from result like "DELETE 5"
        deleted_count = int(result.split()[-1]) if result and result.startswith("DELETE") else 0
        
        if deleted_count > 0:
            log_event(logger, "expired_invitations_cleaned",
                     count=deleted_count)
        
        return deleted_count
        
    except Exception as e:
        log_error(logger, e, "cleanup_invitations_error")
        return 0
