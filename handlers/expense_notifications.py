"""
Telegram-обработчики уведомлений о расходах проекта (feature_110):

  - кнопки под уведомлением о новом расходе:
        👁 Посмотреть          → expnotif_view_{expense_id}
        ⚠️ Это дубликат        → expreport_{expense_id}
        🔕 Настройки уведомлений → expnotif_settings
  - реакция автора/владельца на отметку дубликата:
        🗑 Удалить расход       → repdel_{report_id}_{expense_id}
        ✅ Оставить расход      → repkeep_{report_id}_{expense_id}
  - меню настроек уведомлений участника в проекте:
        🔔 Все расходы / 💰 Только крупные / 🔕 Не уведомлять
        (для «Только крупные» запрашивается сумма порога)

Права проверяются на каждом callback заново (а не по ранее показанному меню):
  - просмотр расхода — участник с правом VIEW_HISTORY;
  - отметка дубликата — участник с правом VIEW_HISTORY;
  - удаление расхода — автор / владелец / участник с правом DELETE_EXPENSE;
  - изменение настроек уведомлений — только сам участник для себя.
"""

from decimal import Decimal, InvalidOperation

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes,
    CallbackQueryHandler,
    ConversationHandler,
    CommandHandler,
    MessageHandler,
    filters,
)

import config
import metrics
from utils import (
    duplicate_reports,
    excel,
    expense_formatter,
    helpers,
    project_notifications,
    project_notifier,
    projects,
)
from utils.helpers import main_menu_button_regex
from utils.logger import get_logger, log_event, log_error
from utils.permissions import Permission, has_permission

logger = get_logger("handlers.expense_notifications")

# Состояние диалога ввода порога крупного расхода
ENTERING_LARGE_THRESHOLD = range(1)


# ---------------------------------------------------------------------------
# Кнопки уведомления: Посмотреть / Это дубликат
# ---------------------------------------------------------------------------

async def view_expense_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """«👁 Посмотреть» из уведомления — показывает детали расхода (alert)."""
    query = update.callback_query
    user_id = update.effective_user.id
    # expnotif_view_{expense_id}
    try:
        expense_id = int(query.data.split("_")[-1])
    except ValueError:
        await query.answer("Некорректные данные.", show_alert=True)
        return

    expense = await excel.get_expense_by_id(expense_id)
    if expense is None:
        await query.answer("Расход не найден или был удалён.", show_alert=True)
        return

    project_id = expense.get("project_id")
    # Право просмотра проверяем заново
    if project_id is not None and not await has_permission(user_id, project_id, Permission.VIEW_HISTORY):
        await query.answer("У вас нет доступа к этому расходу.", show_alert=True)
        return

    author_name = await _safe_user_name(context.bot, expense.get("user_id"))
    details = expense_formatter.format_expense_details(expense, author_name)
    await query.answer()
    # Показываем детали отдельным сообщением, чтобы не затирать уведомление
    await query.message.reply_text(details)


async def report_duplicate_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    «⚠️ Это дубликат» — отмечает расход как возможный дубликат.

    Не удаляет расход. Создаёт отметку (один пользователь — одна отметка) и
    уведомляет автора и владельца проекта.
    """
    query = update.callback_query
    user_id = update.effective_user.id
    # expreport_{expense_id}
    try:
        expense_id = int(query.data.split("_")[-1])
    except ValueError:
        await query.answer("Некорректные данные.", show_alert=True)
        return

    expense = await excel.get_expense_by_id(expense_id)
    if expense is None:
        await query.answer("Расход не найден или уже удалён.", show_alert=True)
        return

    project_id = expense.get("project_id")
    # Отметить как дубликат может участник с правом просмотра
    if project_id is None or not await has_permission(user_id, project_id, Permission.VIEW_HISTORY):
        await query.answer("У вас нет доступа к этому расходу.", show_alert=True)
        return

    # Нельзя отметить свой собственный расход дубликатом
    if str(expense.get("user_id")) == str(user_id):
        await query.answer("Нельзя отметить собственный расход.", show_alert=True)
        return

    # Повторная отметка тем же пользователем не создаётся
    if await duplicate_reports.has_open_report(expense_id, user_id):
        await query.answer("Вы уже отметили этот расход.", show_alert=True)
        return

    report_id = await duplicate_reports.create_report(expense_id, user_id)
    if report_id is None:
        # Либо гонка (уже есть отметка), либо расход исчез
        await query.answer("Не удалось отметить расход (возможно, уже отмечен).", show_alert=True)
        return

    metrics.track_expense_reported_as_duplicate()
    log_event(logger, "expense_reported_as_duplicate",
              expense_id=expense_id, report_id=report_id, reported_by_user_id=user_id,
              project_id=project_id)

    await query.answer("Отметка отправлена автору расхода.", show_alert=True)

    # Уведомляем автора и владельца (ошибки изолированы внутри сервиса)
    try:
        await project_notifier.notify_duplicate_reported(
            context.bot, expense_id=expense_id, report_id=report_id, reporter_id=user_id
        )
    except Exception as e:
        log_error(logger, e, "notify_duplicate_reported_error",
                  expense_id=expense_id, report_id=report_id)


# ---------------------------------------------------------------------------
# Реакция автора/владельца на отметку дубликата: Удалить / Оставить
# ---------------------------------------------------------------------------

async def report_delete_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """«🗑 Удалить расход» — удаляет расход (soft delete) при наличии прав."""
    query = update.callback_query
    user_id = update.effective_user.id
    # repdel_{report_id}_{expense_id}
    parts = query.data.split("_")
    try:
        report_id = int(parts[1])
        expense_id = int(parts[2])
    except (IndexError, ValueError):
        await query.answer("Некорректные данные.", show_alert=True)
        return

    expense = await excel.get_expense_by_id(expense_id, include_deleted=True)
    if expense is None:
        await query.answer("Расход не найден.", show_alert=True)
        return

    # Уже удалён?
    if expense.get("deleted_at") is not None:
        await query.answer()
        await query.edit_message_text("Расход уже удалён.")
        return

    project_id = expense.get("project_id")
    # Удалять может автор, владелец или участник с правом DELETE_EXPENSE
    is_author = str(expense.get("user_id")) == str(user_id)
    can_delete = is_author
    if not can_delete and project_id is not None:
        can_delete = await has_permission(user_id, project_id, Permission.DELETE_EXPENSE)

    if not can_delete:
        await query.answer("У вас нет прав на удаление расхода.", show_alert=True)
        return

    await query.answer()
    deleted = await excel.soft_delete_expense(expense_id)
    if deleted:
        await duplicate_reports.resolve_report(report_id, user_id, config.DuplicateReportStatus.DELETED)
        log_event(logger, "duplicate_report_resolved",
                  report_id=report_id, expense_id=expense_id,
                  status=config.DuplicateReportStatus.DELETED, resolved_by_user_id=user_id)
        await query.edit_message_text("🗑 Расход удалён.")
    else:
        await query.edit_message_text("Расход уже удалён.")


async def report_keep_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """«✅ Оставить расход» — помечает обращение рассмотренным, расход не меняет."""
    query = update.callback_query
    user_id = update.effective_user.id
    # repkeep_{report_id}_{expense_id}
    parts = query.data.split("_")
    try:
        report_id = int(parts[1])
        expense_id = int(parts[2])
    except (IndexError, ValueError):
        await query.answer("Некорректные данные.", show_alert=True)
        return

    expense = await excel.get_expense_by_id(expense_id, include_deleted=True)
    if expense is None:
        await query.answer("Расход не найден.", show_alert=True)
        return

    project_id = expense.get("project_id")
    # Решение по обращению принимает автор или владелец/участник с правом удаления
    is_author = str(expense.get("user_id")) == str(user_id)
    can_resolve = is_author
    if not can_resolve and project_id is not None:
        can_resolve = await has_permission(user_id, project_id, Permission.DELETE_EXPENSE)

    if not can_resolve:
        await query.answer("У вас нет прав на это действие.", show_alert=True)
        return

    await query.answer()
    resolved = await duplicate_reports.resolve_report(report_id, user_id, config.DuplicateReportStatus.KEPT)
    if resolved:
        log_event(logger, "duplicate_report_resolved",
                  report_id=report_id, expense_id=expense_id,
                  status=config.DuplicateReportStatus.KEPT, resolved_by_user_id=user_id)
        await query.edit_message_text("✅ Расход оставлен без изменений.")
    else:
        await query.edit_message_text("Обращение уже рассмотрено.")


# ---------------------------------------------------------------------------
# Меню настроек уведомлений участника
# ---------------------------------------------------------------------------

def _settings_keyboard(project_id: int) -> InlineKeyboardMarkup:
    """Клавиатура выбора режима уведомлений."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(config.PROJECT_NOTIFY_MENU_BUTTONS["all"],
                              callback_data=f"projnotify_set_{project_id}_all")],
        [InlineKeyboardButton(config.PROJECT_NOTIFY_MENU_BUTTONS["large"],
                              callback_data=f"projnotify_set_{project_id}_large_only")],
        [InlineKeyboardButton(config.PROJECT_NOTIFY_MENU_BUTTONS["disabled"],
                              callback_data=f"projnotify_set_{project_id}_disabled")],
        [InlineKeyboardButton(config.PROJECT_NOTIFY_MENU_BUTTONS["back"],
                              callback_data=f"proj_settings_{project_id}")],
    ])


async def _render_settings(query, project_id: int, user_id: int) -> None:
    """Показывает текущий режим и кнопки выбора."""
    settings = await project_notifications.get_member_settings(project_id, user_id)
    mode = settings.get("expense_notify_mode", config.ExpenseNotifyMode.DEFAULT)
    mode_name = project_notifications.mode_display_name(mode)

    text_lines = ["🔔 Уведомления о новых расходах", "", f"Текущий режим: {mode_name}"]
    if mode == config.ExpenseNotifyMode.LARGE_ONLY and settings.get("large_expense_threshold"):
        threshold = expense_formatter.format_amount(settings["large_expense_threshold"])
        text_lines.append(f"Порог: {threshold} ₽")

    await query.edit_message_text("\n".join(text_lines), reply_markup=_settings_keyboard(project_id))


async def open_settings_from_notification(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """«🔕 Настройки уведомлений» из уведомления о расходе."""
    query = update.callback_query
    user_id = update.effective_user.id

    # Определяем активный проект пользователя
    project_id = await helpers.get_active_project_id(user_id, context)
    if project_id is None:
        await query.answer("Сначала выберите проект.", show_alert=True)
        return

    # Доступ к проекту проверяем заново
    if not await projects.is_project_member(user_id, project_id):
        await query.answer("Нет доступа к проекту.", show_alert=True)
        return

    await query.answer()
    await _render_settings(query, project_id, user_id)


async def open_settings_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """«🔔 Уведомления» из меню управления проектом (proj_notify_{project_id})."""
    query = update.callback_query
    user_id = update.effective_user.id
    # proj_notify_{project_id}
    try:
        project_id = int(query.data.split("_")[-1])
    except ValueError:
        await query.answer("Некорректные данные.", show_alert=True)
        return

    if not await projects.is_project_member(user_id, project_id):
        await query.answer("Нет доступа к проекту.", show_alert=True)
        return

    await query.answer()
    context.user_data["active_project_id"] = project_id
    await _render_settings(query, project_id, user_id)


async def set_notify_mode_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Применяет выбранный режим. Для large_only запускает диалог ввода порога.
    callback: projnotify_set_{project_id}_{mode}
    """
    query = update.callback_query
    user_id = update.effective_user.id
    # projnotify_set_{project_id}_{mode}; mode может содержать '_' (large_only)
    parts = query.data.split("_", 3)
    try:
        project_id = int(parts[2])
        mode = parts[3]
    except (IndexError, ValueError):
        await query.answer("Некорректные данные.", show_alert=True)
        return ConversationHandler.END

    # Менять настройки можно только для себя и только будучи участником проекта
    if not await projects.is_project_member(user_id, project_id):
        await query.answer("Нет доступа к проекту.", show_alert=True)
        return ConversationHandler.END

    if mode == config.ExpenseNotifyMode.LARGE_ONLY:
        # Запрашиваем сумму порога
        await query.answer()
        context.user_data["notify_threshold_project_id"] = project_id
        await query.edit_message_text(
            "💰 Введите сумму порога для крупных расходов (в валюте проекта).\n"
            "Например: 1000\n\n"
            "Отправьте /cancel для отмены."
        )
        return ENTERING_LARGE_THRESHOLD

    # ALL / DISABLED — применяем сразу
    ok = await project_notifications.set_notify_mode(project_id, user_id, mode)
    if ok:
        await query.answer("Сохранено.")
        await _render_settings(query, project_id, user_id)
    else:
        await query.answer("Не удалось сохранить.", show_alert=True)
    return ConversationHandler.END


async def handle_threshold_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Принимает и валидирует сумму порога для режима large_only."""
    user_id = update.effective_user.id
    project_id = context.user_data.get("notify_threshold_project_id")
    text = update.message.text.strip().replace(",", ".")

    if project_id is None:
        await update.message.reply_text("❌ Контекст настройки потерян. Откройте настройки заново.")
        return ConversationHandler.END

    # Доступ проверяем заново
    if not await projects.is_project_member(user_id, project_id):
        await update.message.reply_text("❌ Нет доступа к проекту.")
        context.user_data.pop("notify_threshold_project_id", None)
        return ConversationHandler.END

    # Валидация суммы: положительное число
    try:
        threshold = Decimal(text)
    except (InvalidOperation, ValueError):
        await update.message.reply_text("❌ Неверный формат суммы. Введите число, например: 1000")
        return ENTERING_LARGE_THRESHOLD

    if threshold <= 0:
        await update.message.reply_text("❌ Порог должен быть больше нуля. Введите сумму:")
        return ENTERING_LARGE_THRESHOLD

    ok = await project_notifications.set_notify_mode(
        project_id, user_id, config.ExpenseNotifyMode.LARGE_ONLY, large_expense_threshold=threshold
    )
    context.user_data.pop("notify_threshold_project_id", None)

    if ok:
        threshold_str = expense_formatter.format_amount(threshold)
        await update.message.reply_text(
            f"✅ Режим «Только крупные» включён.\n"
            f"Порог: {threshold_str} ₽",
            reply_markup=helpers.get_main_menu_keyboard(),
        )
    else:
        await update.message.reply_text(
            "❌ Не удалось сохранить настройку.",
            reply_markup=helpers.get_main_menu_keyboard(),
        )
    return ConversationHandler.END


async def cancel_threshold(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Отмена ввода порога."""
    context.user_data.pop("notify_threshold_project_id", None)
    await update.message.reply_text(
        "Настройка отменена.",
        reply_markup=helpers.get_main_menu_keyboard(),
    )
    return ConversationHandler.END


# ---------------------------------------------------------------------------
# Вспомогательное
# ---------------------------------------------------------------------------

async def _safe_user_name(bot, user_id):
    """Безопасно получает имя пользователя (или None)."""
    if user_id is None:
        return None
    try:
        chat = await bot.get_chat(int(user_id))
        return getattr(chat, "first_name", None) or getattr(chat, "username", None)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Регистрация
# ---------------------------------------------------------------------------

def register_expense_notification_handlers(application) -> None:
    """Регистрирует все обработчики уведомлений/отметок дубликатов."""
    # Кнопки под уведомлением о новом расходе
    application.add_handler(CallbackQueryHandler(view_expense_callback, pattern=r"^expnotif_view_\d+$"))
    application.add_handler(CallbackQueryHandler(report_duplicate_callback, pattern=r"^expreport_\d+$"))

    # Реакция автора/владельца на отметку
    application.add_handler(CallbackQueryHandler(report_delete_callback, pattern=r"^repdel_\d+_\d+$"))
    application.add_handler(CallbackQueryHandler(report_keep_callback, pattern=r"^repkeep_\d+_\d+$"))

    # Меню настроек уведомлений из проекта
    application.add_handler(CallbackQueryHandler(open_settings_menu, pattern=r"^proj_notify_\d+$"))

    # Диалог выбора режима + ввод порога. entry_points покрывают и кнопку из
    # уведомления (expnotif_settings), и выбор режима из меню настроек.
    settings_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(set_notify_mode_callback, pattern=r"^projnotify_set_\d+_(all|large_only|disabled)$"),
        ],
        states={
            ENTERING_LARGE_THRESHOLD: [
                CommandHandler("cancel", cancel_threshold),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_threshold_input),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel_threshold),
            MessageHandler(filters.Regex(main_menu_button_regex("main_menu")), cancel_threshold),
        ],
        name="project_notify_settings_conversation",
        persistent=False,
    )
    application.add_handler(settings_conv)

    # «🔕 Настройки уведомлений» из уведомления о расходе (открывает меню режимов)
    application.add_handler(CallbackQueryHandler(open_settings_from_notification, pattern=r"^expnotif_settings$"))
