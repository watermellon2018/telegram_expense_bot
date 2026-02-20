"""
Handlers for project invitation system.
Processes invitation tokens from /start command.
"""

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler, ConversationHandler, MessageHandler, filters
from utils import projects, helpers
from utils.logger import get_logger, log_event, log_error
from utils.permissions import get_role_description, get_role_permissions_list
import config

logger = get_logger("handlers.invitations")

# Conversation states
SELECTING_ROLE = range(1)


async def handle_start_with_invitation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle /start command with invitation token: /start inv_TOKEN
    Automatically processes the invitation and adds user to project.
    """
    user_id = update.effective_user.id
    
    # Check if there's an invitation token in the command
    if not context.args or len(context.args) == 0:
        return  # Normal /start command, handled elsewhere
    
    arg = context.args[0]
    
    # Check if this is an invitation token (starts with inv_)
    if not arg.startswith('inv_'):
        return  # Not an invitation, ignore
    
    # Extract token (remove inv_ prefix)
    token = arg[4:]  # Remove "inv_" prefix
    
    log_event(logger, "invitation_token_received", user_id=user_id,
             token_preview=token[:8] if len(token) >= 8 else token)
    
    # Process the invitation
    result = await projects.accept_invitation(user_id, token)
    
    if result['success']:
        # Update context so the active project is immediately available
        context.user_data['active_project_id'] = result['project_id']

        # Success message
        role_emoji = get_role_description(result['role'])

        message = (
            f"✅ {result['message']}\n\n"
            f"📁 Проект: {result['project_name']}\n"
            f"{role_emoji}\n\n"
            f"Теперь вы можете добавлять расходы и просматривать статистику проекта."
        )

        # Show main menu
        await update.message.reply_text(
            message,
            reply_markup=helpers.get_main_menu_keyboard()
        )
        
        log_event(logger, "invitation_accepted_success", user_id=user_id,
                 project_id=result['project_id'],
                 role=result['role'])
    else:
        # Error message
        await update.message.reply_text(
            f"❌ {result['message']}\n\n"
            f"Если у вас есть вопросы, обратитесь к владельцу проекта.",
            reply_markup=helpers.get_main_menu_keyboard()
        )
        
        log_event(logger, "invitation_acceptance_failed", user_id=user_id,
                 reason=result['message'])


async def create_invitation_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Handle /invite command to create a project invitation.
    Usage: /invite <role>
    """
    user_id = update.effective_user.id
    
    # Get active project
    active_project_id = context.user_data.get('active_project_id')
    
    if active_project_id is None:
        await update.message.reply_text(
            "❌ Нет активного проекта.\n"
            "Сначала выберите проект командой /projects или создайте новый."
        )
        return ConversationHandler.END
    
    # Check if user is the owner
    project = await projects.get_project_by_id(user_id, active_project_id)
    if not project or not project['is_owner']:
        await update.message.reply_text(
            "❌ Только владелец проекта может приглашать участников."
        )
        return ConversationHandler.END
    
    # If role is provided in command, use it
    if context.args and len(context.args) > 0:
        role = context.args[0].lower()
        
        if role not in ['editor', 'viewer']:
            await update.message.reply_text(
                "❌ Неверная роль. Используйте 'editor' или 'viewer'.\n\n"
                "Использование: /invite <role>"
            )
            return ConversationHandler.END
        
        # Create invitation directly
        await send_invitation(update, context, active_project_id, role)
        return ConversationHandler.END
    
    # Show role selection
    keyboard = [
        [
            InlineKeyboardButton("✏️ Редактор", callback_data="invite_editor"),
            InlineKeyboardButton("👁️ Наблюдатель", callback_data="invite_viewer")
        ],
        [InlineKeyboardButton("❌ Отмена", callback_data="invite_cancel")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"📁 Проект: {project['project_name']}\n\n"
        f"Выберите роль для приглашаемого участника:\n\n"
        f"✏️ **Редактор** - может добавлять расходы и категории\n"
        f"👁️ **Наблюдатель** - может только просматривать данные",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )
    
    return SELECTING_ROLE


async def handle_role_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Handle role selection for invitation.
    """
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    callback_data = query.data
    
    if callback_data == "invite_cancel":
        await query.edit_message_text("❌ Создание приглашения отменено.")
        return ConversationHandler.END
    
    # Extract role from callback
    if callback_data.startswith("invite_"):
        role = callback_data.split("_")[1]
    else:
        await query.edit_message_text("❌ Ошибка выбора роли.")
        return ConversationHandler.END
    
    # Get active project
    active_project_id = context.user_data.get('active_project_id')
    if not active_project_id:
        await query.edit_message_text("❌ Нет активного проекта.")
        return ConversationHandler.END
    
    # Create invitation
    await send_invitation_from_callback(query, context, user_id, active_project_id, role)
    return ConversationHandler.END


async def send_invitation(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    project_id: int,
    role: str
) -> None:
    """
    Create and send invitation link.
    """
    user_id = update.effective_user.id
    
    # Create invitation
    result = await projects.create_invitation(user_id, project_id, role)
    
    if not result['success']:
        await update.message.reply_text(f"❌ {result['message']}")
        return
    
    # Get bot username
    bot = await context.bot.get_me()
    bot_username = bot.username
    
    # Generate invitation link
    invite_link = await projects.get_invitation_link(result['token'], bot_username)
    
    role_emoji = get_role_description(role)
    
    message = (
        f"✅ Приглашение создано!\n\n"
        f"📁 Проект: {result['project_name']}\n"
        f"{role_emoji}\n\n"
        f"Отправьте эту ссылку участнику:\n"
        f'<a href="{invite_link}">🔗 Перейти в проект</a>\n\n'
        f"⏰ Действительна до: {result['expires_at'][:16].replace('T', ' ')}\n\n"
        f"Участник будет добавлен в проект после перехода по ссылке."
    )

    await update.message.reply_text(message, parse_mode='HTML')
    
    log_event(logger, "invitation_link_created", user_id=user_id,
             project_id=project_id, role=role)


async def send_invitation_from_callback(
    query,
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    project_id: int,
    role: str
) -> None:
    """
    Create and send invitation link from callback query.
    """
    # Create invitation
    result = await projects.create_invitation(user_id, project_id, role)
    
    if not result['success']:
        await query.edit_message_text(f"❌ {result['message']}")
        return
    
    # Get bot username
    bot = await context.bot.get_me()
    bot_username = bot.username
    
    # Generate invitation link
    invite_link = await projects.get_invitation_link(result['token'], bot_username)
    
    role_emoji = get_role_description(role)
    
    message = (
        f"✅ Приглашение создано!\n\n"
        f"📁 Проект: {result['project_name']}\n"
        f"{role_emoji}\n\n"
        f"Отправьте эту ссылку участнику:\n"
        f'<a href="{invite_link}">🔗 Перейти в проект</a>\n\n'
        f"⏰ Действительна до: {result['expires_at'][:16].replace('T', ' ')}\n\n"
        f"Участник будет добавлен в проект после перехода по ссылке."
    )

    await query.edit_message_text(message, parse_mode='HTML')
    
    log_event(logger, "invitation_link_created", user_id=user_id,
             project_id=project_id, role=role)


async def list_members_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle /members command to list project members.
    """
    user_id = update.effective_user.id
    
    # Get active project
    active_project_id = context.user_data.get('active_project_id')
    
    if active_project_id is None:
        await update.message.reply_text(
            "❌ Нет активного проекта.\n"
            "Сначала выберите проект командой /projects."
        )
        return
    
    # Check permission
    from utils.permissions import Permission, has_permission
    if not await has_permission(user_id, active_project_id, Permission.VIEW_MEMBERS):
        await update.message.reply_text(
            "❌ У вас нет прав на просмотр участников проекта."
        )
        return
    
    # Get project info
    project = await projects.get_project_by_id(user_id, active_project_id)
    if not project:
        await update.message.reply_text("❌ Проект не найден.")
        return
    
    # Get members
    members = await projects.get_project_members(active_project_id)
    
    if not members:
        await update.message.reply_text(
            f"📁 Проект: {project['project_name']}\n\n"
            f"Нет участников."
        )
        return
    
    # Format member list
    message = f"📁 Проект: {project['project_name']}\n\n"
    message += f"👥 Участники ({len(members)}):\n\n"
    
    for member in members:
        role_emoji = get_role_description(member['role'])
        
        # Show user ID (in real app, you'd show username/name)
        user_display = f"ID: {member['user_id']}"
        if member['role'] == 'owner':
            user_display += " (вы)" if str(user_id) == member['user_id'] else ""
        
        message += f"{role_emoji}\n{user_display}\n"
        if member['joined_at']:
            message += f"Присоединился: {member['joined_at'][:10]}\n"
        message += "\n"
    
    await update.message.reply_text(message)


def register_invitation_handlers(application):
    """
    Register invitation-related handlers.
    """
    async def _cancel_invite(update, context):
        await update.message.reply_text("Создание приглашения отменено.", reply_markup=helpers.get_main_menu_keyboard())
        return ConversationHandler.END

    # Conversation handler for /invite command
    invite_conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("invite", create_invitation_command),
        ],
        states={
            SELECTING_ROLE: [
                CallbackQueryHandler(handle_role_selection, pattern=r'^invite_')
            ],
        },
        fallbacks=[CommandHandler("cancel", _cancel_invite)],
        name="invite_conversation",
        persistent=False
    )
    application.add_handler(invite_conv_handler)
    
    # /members command
    application.add_handler(CommandHandler("members", list_members_command))
