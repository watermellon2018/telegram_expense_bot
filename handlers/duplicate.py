"""
Telegram-обработчики сценария «возможный дубликат расхода» (feature_110).

Показ предупреждения происходит из диалога добавления расхода
(handlers/expense.py). Здесь — callback-кнопки под предупреждением:

  ✅ Всё равно добавить → dupconfirm_{draft_id}
  ❌ Отменить           → dupcancel_{draft_id}
  👁 Посмотреть расход  → dupview_{draft_id}_{expense_id}
  ⬅️ Назад (из деталей) → dupback_{draft_id}_{expense_id}

Защита:
  - callback может нажать только владелец черновика (тот, кто добавлял расход);
  - повторное/двойное нажатие не создаёт второй расход (idempotency по draft_id);
  - корректно обрабатывается удаление найденного расхода и истёкший черновик.
"""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackQueryHandler, ContextTypes

import metrics
from utils import excel, expense_creation, expense_formatter
from utils.logger import get_logger, log_event

logger = get_logger("handlers.duplicate")


def build_duplicate_warning_keyboard(draft_id: str, existing_expense_id: int) -> InlineKeyboardMarkup:
    """Inline-клавиатура под предупреждением о возможном дубликате."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Всё равно добавить", callback_data=f"dupconfirm_{draft_id}")],
        [InlineKeyboardButton("👁 Посмотреть расход",
                              callback_data=f"dupview_{draft_id}_{existing_expense_id}")],
        [InlineKeyboardButton("❌ Отменить", callback_data=f"dupcancel_{draft_id}")],
    ])


def _confirm_keyboard(draft_id: str, existing_expense_id: int) -> InlineKeyboardMarkup:
    """Клавиатура возврата к подтверждению (после просмотра деталей)."""
    return build_duplicate_warning_keyboard(draft_id, existing_expense_id)


async def _verify_owner(update: Update, draft: dict) -> bool:
    """Проверяет, что callback нажал владелец черновика."""
    user_id = update.effective_user.id
    return draft is not None and str(draft.get("owner_user_id")) == str(user_id)


async def dup_confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """«✅ Всё равно добавить» — создаёт расход без повторной проверки."""
    query = update.callback_query
    draft_id = query.data.split("_", 1)[1]

    draft = expense_creation.get_draft(context.bot_data, draft_id)

    # Истёкший/отсутствующий черновик
    if draft is None:
        await query.answer("Запрос устарел.", show_alert=True)
        try:
            await query.edit_message_text("⌛️ Запрос устарел. Добавьте расход заново.")
        except Exception:
            pass
        return

    # Только владелец может подтвердить
    if not await _verify_owner(update, draft):
        await query.answer("Это действие доступно только автору.", show_alert=True)
        return

    await query.answer()

    result = await expense_creation.confirm_pending_expense(
        context.bot, draft_id=draft_id, bot_data=context.bot_data
    )

    status = result.get("status")
    if status == "created":
        # Расход успешно создан — убираем черновик
        expense_creation.discard_draft(context.bot_data, draft_id)
        await query.edit_message_text("✅ Расход добавлен.")
    elif status == "already":
        # Повторное нажатие — расход уже был создан, второй не создаём
        expense_creation.discard_draft(context.bot_data, draft_id)
        await query.edit_message_text("✅ Расход уже добавлен.")
    elif status == "expired":
        await query.edit_message_text("⌛️ Запрос устарел. Добавьте расход заново.")
    else:
        await query.edit_message_text("❌ Не удалось добавить расход. Попробуйте ещё раз.")


async def dup_cancel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """«❌ Отменить» — завершает сценарий без создания расхода."""
    query = update.callback_query
    draft_id = query.data.split("_", 1)[1]

    draft = expense_creation.get_draft(context.bot_data, draft_id)
    if draft is None:
        await query.answer()
        try:
            await query.edit_message_text("Отменено.")
        except Exception:
            pass
        return

    if not await _verify_owner(update, draft):
        await query.answer("Это действие доступно только автору.", show_alert=True)
        return

    await query.answer()
    expense_creation.discard_draft(context.bot_data, draft_id)
    metrics.track_duplicate_cancelled()
    log_event(logger, "possible_expense_duplicate_cancelled", draft_id=draft_id,
              user_id=update.effective_user.id)
    await query.edit_message_text("❌ Добавление расхода отменено.")


async def dup_view_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """«👁 Посмотреть расход» — показывает детали найденного расхода + возврат."""
    query = update.callback_query
    # dupview_{draft_id}_{expense_id}
    parts = query.data.split("_")
    draft_id = parts[1]
    try:
        existing_expense_id = int(parts[2])
    except (IndexError, ValueError):
        await query.answer("Некорректные данные.", show_alert=True)
        return

    draft = expense_creation.get_draft(context.bot_data, draft_id)
    if draft is None:
        await query.answer("Запрос устарел.", show_alert=True)
        try:
            await query.edit_message_text("⌛️ Запрос устарел. Добавьте расход заново.")
        except Exception:
            pass
        return

    if not await _verify_owner(update, draft):
        await query.answer("Это действие доступно только автору.", show_alert=True)
        return

    await query.answer()

    expense = await excel.get_expense_by_id(existing_expense_id)
    if expense is None:
        # Расход был удалён до нажатия кнопки — корректно сообщаем и оставляем
        # возможность всё равно добавить/отменить.
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Всё равно добавить", callback_data=f"dupconfirm_{draft_id}")],
            [InlineKeyboardButton("❌ Отменить", callback_data=f"dupcancel_{draft_id}")],
        ])
        await query.edit_message_text(
            "Найденный расход уже удалён.\n\nВы всё равно хотите добавить новый расход?",
            reply_markup=keyboard,
        )
        return

    author_name = None
    try:
        author_name = await _safe_user_name(context.bot, expense.get("user_id"))
    except Exception:
        author_name = None

    details = expense_formatter.format_expense_details(expense, author_name)
    keyboard = _confirm_keyboard(draft_id, existing_expense_id)
    await query.edit_message_text(
        details + "\n\nВы всё равно хотите добавить новый расход?",
        reply_markup=keyboard,
    )


async def _safe_user_name(bot, user_id):
    """Безопасно получает имя пользователя для деталей расхода."""
    if user_id is None:
        return None
    try:
        chat = await bot.get_chat(int(user_id))
        return getattr(chat, "first_name", None) or getattr(chat, "username", None)
    except Exception:
        return None


def register_duplicate_handlers(application) -> None:
    """Регистрирует callback-обработчики сценария дубликатов."""
    application.add_handler(CallbackQueryHandler(dup_confirm_callback, pattern=r"^dupconfirm_[0-9a-f]+$"))
    application.add_handler(CallbackQueryHandler(dup_cancel_callback, pattern=r"^dupcancel_[0-9a-f]+$"))
    application.add_handler(CallbackQueryHandler(dup_view_callback, pattern=r"^dupview_[0-9a-f]+_\d+$"))
