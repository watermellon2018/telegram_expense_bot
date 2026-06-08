"""
Enhanced project management UI with Telegram buttons.
Handles member management, invitations, and role changes with inline keyboards.
"""

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler, ConversationHandler, MessageHandler, filters
from utils import projects, helpers
from utils.logger import get_logger, log_event, log_error
from utils.permissions import Permission, has_permission, get_role_description
import config

logger = get_logger("handlers.project_management")

# Conversation states
CONFIRMING_LEAVE = range(1)


async def project_settings_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Show project settings menu with management options.
    Available options depend on user's role.
    """
    user_id = update.effective_user.id
    
    # Get active project
    active_project_id = context.user_data.get('active_project_id')
    
    if active_project_id is None:
        message_text = (
            "❌ Нет активного проекта.\n"
            "Сначала выберите проект командой /projects или создайте новый."
        )
        if update.callback_query:
            await update.callback_query.edit_message_text(message_text)
        else:
            await update.message.reply_text(message_text)
        return
    
    # Get project details
    project = await projects.get_project_by_id(user_id, active_project_id)
    if not project:
        message_text = "❌ Проект не найден."
        if update.callback_query:
            await update.callback_query.edit_message_text(message_text)
        else:
            await update.message.reply_text(message_text)
        return
    
    # Get user's role
    role = project['role']
    is_owner = project['is_owner']
    
    # Build keyboard based on role
    keyboard = []
    
    # All members can view members
    keyboard.append([InlineKeyboardButton("👥 Участники проекта", callback_data=f"proj_members_{active_project_id}")])

    # All members manage their own expense notification settings (feature_110)
    keyboard.append([InlineKeyboardButton("🔔 Уведомления о расходах", callback_data=f"proj_notify_{active_project_id}")])

    # Owner-specific options
    if is_owner:
        keyboard.append([InlineKeyboardButton("✉️ Пригласить участника", callback_data=f"proj_invite_{active_project_id}")])
        keyboard.append([InlineKeyboardButton("⚙️ Управление ролями", callback_data=f"proj_roles_{active_project_id}")])

    # Non-owners can leave project
    if not is_owner:
        keyboard.append([InlineKeyboardButton("🚪 Покинуть проект", callback_data=f"proj_leave_{active_project_id}")])
    
    # Project info
    stats = await projects.get_project_stats(user_id, active_project_id)
    members = await projects.get_project_members(active_project_id)
    
    role_emoji = get_role_description(role)
    
    message = (
        f"⚙️ Управление проектом\n\n"
        f"📁 {project['project_name']}\n"
        f"{role_emoji}\n\n"
        f"📊 Статистика:\n"
        f"• Расходов: {stats['count']}\n"
        f"• Сумма: {stats['total']:.2f}\n"
        f"• Участников: {len(members)}\n\n"
        f"Выберите действие:"
    )
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Handle both callback queries and regular messages
    if update.callback_query:
        await update.callback_query.edit_message_text(message, reply_markup=reply_markup)
    else:
        await update.message.reply_text(message, reply_markup=reply_markup)
    
    log_event(logger, "project_settings_opened", user_id=user_id,
             project_id=active_project_id, role=role)


async def show_members_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Show list of project members with management buttons for owners.
    """
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    callback_data = query.data
    
    # Extract project_id from callback
    project_id = int(callback_data.split('_')[-1])
    
    # Check permission
    if not await has_permission(user_id, project_id, Permission.VIEW_MEMBERS):
        await query.edit_message_text("❌ У вас нет прав на просмотр участников.")
        return
    
    # Get project and members
    project = await projects.get_project_by_id(user_id, project_id)
    if not project:
        await query.edit_message_text("❌ Проект не найден.")
        return
    
    members = await projects.get_project_members(project_id)
    
    if not members:
        await query.edit_message_text(
            f"📁 {project['project_name']}\n\n"
            f"❌ Нет участников."
        )
        return
    
    # Build message with member list
    message = f"📁 {project['project_name']}\n\n"
    message += f"👥 Участники ({len(members)}):\n\n"
    
    keyboard = []
    
    for member in members:
        role_emoji = get_role_description(member['role'])
        member_user_id = member['user_id']
        
        # Show user info
        user_display = f"ID: {member_user_id}"
        if member['role'] == 'owner':
            user_display += " (владелец)"
        elif str(user_id) == member_user_id:
            user_display += " (вы)"
        
        message += f"{role_emoji}\n{user_display}\n"
        if member['joined_at']:
            message += f"Присоединился: {member['joined_at'][:10]}\n"
        
        # Add management buttons for owners (except for themselves and other owner)
        if project['is_owner'] and member['role'] != 'owner' and str(user_id) != member_user_id:
            row = [
                InlineKeyboardButton(
                    f"👤 {member_user_id[:8]}...",
                    callback_data=f"member_info_{project_id}_{member_user_id}"
                ),
                InlineKeyboardButton(
                    "🔄 Роль",
                    callback_data=f"member_role_{project_id}_{member_user_id}"
                ),
                InlineKeyboardButton(
                    "❌ Удалить",
                    callback_data=f"member_kick_{project_id}_{member_user_id}"
                )
            ]
            keyboard.append(row)
        
        message += "\n"
    
    # Back button
    keyboard.append([InlineKeyboardButton("« Назад", callback_data=f"proj_settings_{project_id}")])
    
    reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None
    await query.edit_message_text(message, reply_markup=reply_markup)
    
    log_event(logger, "members_list_viewed", user_id=user_id,
             project_id=project_id, members_count=len(members))


async def show_invite_dialog(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Show invitation creation dialog with role selection.
    """
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    callback_data = query.data
    
    # Extract project_id from callback
    project_id = int(callback_data.split('_')[-1])
    
    # Check permission (owner only)
    if not await has_permission(user_id, project_id, Permission.INVITE_MEMBERS):
        await query.edit_message_text("❌ Только владелец может приглашать участников.")
        return
    
    # Get project
    project = await projects.get_project_by_id(user_id, project_id)
    if not project:
        await query.edit_message_text("❌ Проект не найден.")
        return
    
    # Build role selection keyboard
    keyboard = [
        [
            InlineKeyboardButton("✏️ Редактор", callback_data=f"invite_create_{project_id}_editor"),
            InlineKeyboardButton("👁️ Наблюдатель", callback_data=f"invite_create_{project_id}_viewer")
        ],
        [InlineKeyboardButton("« Назад", callback_data=f"proj_settings_{project_id}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    message = (
        f"✉️ Приглашение в проект\n\n"
        f"📁 {project['project_name']}\n\n"
        f"Выберите роль для нового участника:\n\n"
        f"✏️ **Редактор** - может добавлять расходы и категории\n"
        f"👁️ **Наблюдатель** - может только просматривать данные"
    )
    
    await query.edit_message_text(message, reply_markup=reply_markup, parse_mode='Markdown')


async def create_invitation_link(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Create and display invitation link.
    """
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    callback_data = query.data
    
    # Parse callback: invite_create_PROJECT_ID_ROLE
    parts = callback_data.split('_')
    project_id = int(parts[2])
    role = parts[3]
    
    # Create invitation
    result = await projects.create_invitation(user_id, project_id, role, expires_in_hours=24)
    
    if not result['success']:
        await query.edit_message_text(f"❌ {result['message']}")
        return
    
    # Get bot username
    bot = await context.bot.get_me()
    bot_username = bot.username
    
    # Generate link
    invite_link = await projects.get_invitation_link(result['token'], bot_username)
    
    role_emoji = get_role_description(role)
    
    message = (
        f"✅ Приглашение создано!\n\n"
        f"📁 {result['project_name']}\n"
        f"{role_emoji}\n\n"
        f"Отправьте эту ссылку участнику:\n"
        f'<a href="{invite_link}">🔗 Перейти в проект</a>\n\n'
        f"⏰ Действительна до: {result['expires_at'][:16].replace('T', ' ')}\n\n"
        f"Участник будет добавлен после перехода по ссылке."
    )

    keyboard = [[InlineKeyboardButton("« Назад к настройкам", callback_data=f"proj_settings_{project_id}")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(message, reply_markup=reply_markup, parse_mode='HTML')
    
    log_event(logger, "invitation_created_via_ui", user_id=user_id,
             project_id=project_id, role=role)


async def show_role_management(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Show role management interface for owners.
    """
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    callback_data = query.data
    
    # Extract project_id
    project_id = int(callback_data.split('_')[-1])
    
    # Check permission (owner only)
    if not await has_permission(user_id, project_id, Permission.CHANGE_ROLES):
        await query.edit_message_text("❌ Только владелец может изменять роли.")
        return
    
    # Get project and members
    project = await projects.get_project_by_id(user_id, project_id)
    members = await projects.get_project_members(project_id)
    
    # Filter out owner
    editable_members = [m for m in members if m['role'] != 'owner']
    
    if not editable_members:
        keyboard = [[InlineKeyboardButton("« Назад", callback_data=f"proj_settings_{project_id}")]]
        await query.edit_message_text(
            f"📁 {project['project_name']}\n\n"
            f"Нет участников для управления ролями.",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return
    
    # Build message and keyboard
    message = f"⚙️ Управление ролями\n\n📁 {project['project_name']}\n\n"
    keyboard = []
    
    for member in editable_members:
        role_emoji = get_role_description(member['role'])
        member_user_id = member['user_id']
        
        # Toggle role button
        new_role = 'viewer' if member['role'] == 'editor' else 'editor'
        new_role_emoji = "👁️" if new_role == 'viewer' else "✏️"
        
        message += f"{role_emoji} ID: {member_user_id}\n"
        
        keyboard.append([
            InlineKeyboardButton(
                f"↔️ Изменить на {new_role_emoji}",
                callback_data=f"role_change_{project_id}_{member_user_id}_{new_role}"
            )
        ])
    
    keyboard.append([InlineKeyboardButton("« Назад", callback_data=f"proj_settings_{project_id}")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(message, reply_markup=reply_markup)


async def change_member_role_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle role change callback.
    """
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    callback_data = query.data
    
    # Parse: role_change_PROJECT_ID_MEMBER_ID_NEW_ROLE
    parts = callback_data.split('_')
    project_id = int(parts[2])
    member_id = int(parts[3])
    new_role = parts[4]
    
    # Change role
    result = await projects.change_member_role(user_id, project_id, member_id, new_role)
    
    if result['success']:
        await query.answer("✅ Роль изменена", show_alert=True)
        # Refresh role management view
        context.user_data['callback_query'] = query
        await show_role_management(update, context)
    else:
        await query.answer(f"❌ {result['message']}", show_alert=True)
    
    log_event(logger, "role_changed_via_ui", owner_id=user_id,
             project_id=project_id, member_id=member_id, new_role=new_role)


async def kick_member_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle member kick callback.
    """
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    callback_data = query.data
    
    # Parse: member_kick_PROJECT_ID_MEMBER_ID
    parts = callback_data.split('_')
    project_id = int(parts[2])
    member_id = int(parts[3])
    
    # Show confirmation
    keyboard = [
        [
            InlineKeyboardButton("✅ Да, удалить", callback_data=f"kick_confirm_{project_id}_{member_id}"),
            InlineKeyboardButton("❌ Отмена", callback_data=f"proj_members_{project_id}")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"⚠️ Вы уверены, что хотите удалить участника?\n\n"
        f"ID: {member_id}\n\n"
        f"Участник потеряет доступ к проекту.",
        reply_markup=reply_markup
    )


async def confirm_kick_member(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Confirm and execute member kick.
    """
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    callback_data = query.data
    
    # Parse: kick_confirm_PROJECT_ID_MEMBER_ID
    parts = callback_data.split('_')
    project_id = int(parts[2])
    member_id = int(parts[3])
    
    # Remove member
    result = await projects.remove_member(user_id, project_id, member_id)
    
    if result['success']:
        await query.answer("✅ Участник удален", show_alert=True)
        # Show updated members list
        query.data = f"proj_members_{project_id}"
        await show_members_list(update, context)
    else:
        await query.answer(f"❌ {result['message']}", show_alert=True)
    
    log_event(logger, "member_kicked_via_ui", owner_id=user_id,
             project_id=project_id, member_id=member_id)


async def leave_project_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle leave project callback.
    """
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    callback_data = query.data
    
    # Extract project_id
    project_id = int(callback_data.split('_')[-1])
    
    # Get project
    project = await projects.get_project_by_id(user_id, project_id)
    if not project:
        await query.edit_message_text("❌ Проект не найден.")
        return
    
    # Owners cannot leave
    if project['is_owner']:
        await query.answer(
            "❌ Владелец не может покинуть проект",
            show_alert=True
        )
        return
    
    # Show confirmation
    keyboard = [
        [
            InlineKeyboardButton("✅ Да, покинуть", callback_data=f"leave_confirm_{project_id}"),
            InlineKeyboardButton("❌ Отмена", callback_data=f"proj_settings_{project_id}")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"⚠️ Вы уверены, что хотите покинуть проект?\n\n"
        f"📁 {project['project_name']}\n\n"
        f"Вы потеряете доступ к данным проекта.",
        reply_markup=reply_markup
    )


async def confirm_leave_project(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Confirm and execute leaving project.
    """
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    callback_data = query.data
    
    # Extract project_id
    project_id = int(callback_data.split('_')[-1])
    
    # Leave project
    result = await projects.leave_project(user_id, project_id)
    
    if result['success']:
        # Reset active project if needed
        if context.user_data.get('active_project_id') == project_id:
            context.user_data['active_project_id'] = None

        # edit_message_text only accepts InlineKeyboardMarkup — send ReplyKeyboard separately
        await query.edit_message_text(
            f"✅ {result['message']}\n\n"
            f"Вы больше не являетесь участником проекта."
        )
        await query.message.reply_text(
            "Возврат в главное меню:",
            reply_markup=helpers.get_main_menu_keyboard()
        )
    else:
        await query.edit_message_text(f"❌ {result['message']}")

    log_event(logger, "user_left_via_ui", user_id=user_id, project_id=project_id)


async def back_to_settings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Return to project settings menu.
    """
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    
    # Extract project_id
    project_id = int(query.data.split('_')[-1])
    
    # Store project_id temporarily
    context.user_data['active_project_id'] = project_id
    
    # Get project details
    project = await projects.get_project_by_id(user_id, project_id)
    if not project:
        await query.edit_message_text("❌ Проект не найден.")
        return
    
    # Get user's role
    role = project['role']
    is_owner = project['is_owner']
    
    # Build keyboard based on role
    keyboard = []
    
    # All members can view members
    keyboard.append([InlineKeyboardButton("👥 Участники проекта", callback_data=f"proj_members_{project_id}")])

    # All members manage their own expense notification settings (feature_110)
    keyboard.append([InlineKeyboardButton("🔔 Уведомления о расходах", callback_data=f"proj_notify_{project_id}")])

    # Owner-specific options
    if is_owner:
        keyboard.append([InlineKeyboardButton("✉️ Пригласить участника", callback_data=f"proj_invite_{project_id}")])
        keyboard.append([InlineKeyboardButton("⚙️ Управление ролями", callback_data=f"proj_roles_{project_id}")])

    # Non-owners can leave project
    if not is_owner:
        keyboard.append([InlineKeyboardButton("🚪 Покинуть проект", callback_data=f"proj_leave_{project_id}")])
    
    # Project info
    stats = await projects.get_project_stats(user_id, project_id)
    members = await projects.get_project_members(project_id)
    
    role_emoji = get_role_description(role)
    
    message = (
        f"⚙️ Управление проектом\n\n"
        f"📁 {project['project_name']}\n"
        f"{role_emoji}\n\n"
        f"📊 Статистика:\n"
        f"• Расходов: {stats['count']}\n"
        f"• Сумма: {stats['total']:.2f}\n"
        f"• Участников: {len(members)}\n\n"
        f"Выберите действие:"
    )
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(message, reply_markup=reply_markup)


def register_project_management_handlers(application):
    """
    Register project management handlers with inline keyboards.
    """
    # Settings menu command
    application.add_handler(CommandHandler("project_settings", project_settings_menu))
    
    # Callback query handlers
    application.add_handler(CallbackQueryHandler(show_members_list, pattern=r'^proj_members_\d+$'))
    application.add_handler(CallbackQueryHandler(show_invite_dialog, pattern=r'^proj_invite_\d+$'))
    application.add_handler(CallbackQueryHandler(create_invitation_link, pattern=r'^invite_create_\d+_(editor|viewer)$'))
    application.add_handler(CallbackQueryHandler(show_role_management, pattern=r'^proj_roles_\d+$'))
    application.add_handler(CallbackQueryHandler(change_member_role_callback, pattern=r'^role_change_\d+_\d+_(editor|viewer)$'))
    application.add_handler(CallbackQueryHandler(kick_member_callback, pattern=r'^member_kick_\d+_\d+$'))
    application.add_handler(CallbackQueryHandler(confirm_kick_member, pattern=r'^kick_confirm_\d+_\d+$'))
    application.add_handler(CallbackQueryHandler(leave_project_callback, pattern=r'^proj_leave_\d+$'))
    application.add_handler(CallbackQueryHandler(confirm_leave_project, pattern=r'^leave_confirm_\d+$'))
    application.add_handler(CallbackQueryHandler(back_to_settings, pattern=r'^proj_settings_\d+$'))
