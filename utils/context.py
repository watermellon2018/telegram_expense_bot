"""Context helpers for Telegram handlers."""

from telegram.ext import ContextTypes

from utils.logger import get_logger, log_event, log_error

logger = get_logger("utils.context")


async def get_active_project_id(user_id: int, context: ContextTypes.DEFAULT_TYPE):
    """
    Return active project id from context cache or load it from DB.
    """
    from utils import projects

    if "active_project_id" in context.user_data:
        return context.user_data["active_project_id"]

    try:
        active_project = await projects.get_active_project(user_id)
        if active_project:
            project_id = active_project["project_id"]
            context.user_data["active_project_id"] = project_id
            log_event(
                logger,
                "active_project_loaded_from_db",
                user_id=user_id,
                project_id=project_id,
            )
            return project_id

        context.user_data["active_project_id"] = None
        return None
    except Exception as e:
        log_error(logger, e, "load_active_project_error", user_id=user_id)
        context.user_data["active_project_id"] = None
        return None
