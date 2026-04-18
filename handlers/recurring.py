"""
Обработчики команд для управления постоянными расходами (recurring expenses).

Структура меню:
  🔁 Постоянные (кнопка в главном меню)
    ↳ Список всех правил с inline-кнопками ⏸ / ▶️ / 🗑
    ↳ [➕ Добавить постоянный расход]

Диалог добавления:
  Сумма → Категория → Комментарий → Частота → Подтверждение

Pattern suggestion:
  После успешного добавления расхода (вызывается из handlers/expense.py)
  бот проверяет паттерн и предлагает создать постоянный расход.
"""

import asyncio
import datetime
from typing import Optional

import config
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardRemove,
)
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)

from utils import categories as cat_utils
from utils import recurring as rec_utils
from utils import pattern_detector as pd_utils
from utils.helpers import get_main_menu_keyboard, main_menu_button_regex
from utils.logger import get_logger, log_event, log_error

logger = get_logger("handlers.recurring")

# ---------------------------------------------------------------------------
# Состояния ConversationHandler
# ---------------------------------------------------------------------------
(
    REC_ENTERING_AMOUNT,
    REC_CHOOSING_CATEGORY,
    REC_ENTERING_COMMENT,
    REC_CHOOSING_FREQUENCY,
    REC_ENTERING_CUSTOM_FREQUENCY,
) = range(5)

(
    REC_EDIT_CHOOSING_FREQUENCY,
    REC_EDIT_ENTERING_CUSTOM_FREQUENCY,
) = range(100, 102)


# ---------------------------------------------------------------------------
# Вспомогательные функции
# ---------------------------------------------------------------------------

def _format_next_run(next_run_at) -> str:
    """Форматирует дату следующего срабатывания для отображения."""
    if next_run_at is None:
        return "—"
    if isinstance(next_run_at, datetime.datetime):
        return next_run_at.strftime("%d.%m.%Y")
    return str(next_run_at)


def _build_rules_message_and_keyboard(rules: list) -> tuple:
    """
    Формирует текст и inline-клавиатуру для экрана списка правил.

    Каждое правило — строка в тексте + ряд кнопок в клавиатуре.
    Возвращает (text: str, InlineKeyboardMarkup).
    """
    if not rules:
        text = (
            "🔁 *Постоянные расходы*\n\n"
            "У тебя пока нет постоянных расходов.\n"
            "Нажми кнопку ниже, чтобы добавить первый."
        )
        keyboard = [[InlineKeyboardButton(
            config.RECURRING_MENU_BUTTONS["add"],
            callback_data="rec_add",
        )]]
        return text, InlineKeyboardMarkup(keyboard)

    lines = ["🔁 *Постоянные расходы*\n"]
    keyboard = []

    for i, rule in enumerate(rules, 1):
        status_icon = "✅" if rule['status'] == 'active' else "⏸"
        freq_text = rec_utils.format_frequency(rule)
        next_run = _format_next_run(rule.get('next_run_at'))
        cat_name = rule.get('category_name', '')
        comment = rule.get('comment') or cat_name

        lines.append(
            f"{i}. {comment} — {rule['amount']}\n"
            f"   📅 {freq_text} | {status_icon}\n"
            f"   Следующее: {next_run}"
        )

        # Кнопки действий для правила
        rule_id = rule['id']
        row = [InlineKeyboardButton(f"{i}", callback_data=f"rec_row_label_{rule_id}")]
        row.append(InlineKeyboardButton("✏️ Изменить", callback_data=f"rec_edit_{rule_id}"))
        if rule['status'] == 'active':
            row.append(InlineKeyboardButton("⏸ Пауза", callback_data=f"rec_pause_{rule_id}"))
        else:
            row.append(InlineKeyboardButton("▶️ Возобновить", callback_data=f"rec_resume_{rule_id}"))
        row.append(InlineKeyboardButton("🗑 Удалить", callback_data=f"rec_delete_{rule_id}"))
        keyboard.append(row)

    keyboard.append([InlineKeyboardButton(
        config.RECURRING_MENU_BUTTONS["add"],
        callback_data="rec_add",
    )])

    return "\n".join(lines), InlineKeyboardMarkup(keyboard)


def _build_category_keyboard(cats: list) -> InlineKeyboardMarkup:
    """Строит inline-клавиатуру выбора категории для добавления правила."""
    keyboard = []
    row = []
    for idx, cat in enumerate(cats):
        emoji = config.DEFAULT_CATEGORIES.get(cat['name'], '📦')
        row.append(InlineKeyboardButton(
            f"{emoji} {cat['name']}",
            callback_data=f"cat_rec_{cat['category_id']}",
        ))
        # 2 кнопки в ряд
        if len(row) == 2 or idx == len(cats) - 1:
            keyboard.append(row)
            row = []
    return InlineKeyboardMarkup(keyboard)


def _build_frequency_keyboard() -> InlineKeyboardMarkup:
    """Строит inline-клавиатуру выбора базовой частоты."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📆 Каждый день",   callback_data="rec_freq_daily"),
            InlineKeyboardButton("📅 Каждую неделю", callback_data="rec_freq_weekly"),
        ],
        [
            InlineKeyboardButton("🗓 Каждый месяц",  callback_data="rec_freq_monthly"),
            InlineKeyboardButton("✏️ Другое...",     callback_data="rec_freq_custom"),
        ],
    ])


def _build_edit_frequency_keyboard() -> InlineKeyboardMarkup:
    """Строит inline-клавиатуру выбора частоты для редактирования правила."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📆 Каждый день",   callback_data="rec_edit_freq_daily"),
            InlineKeyboardButton("📅 Каждую неделю", callback_data="rec_edit_freq_weekly"),
        ],
        [
            InlineKeyboardButton("🗓 Каждый месяц",  callback_data="rec_edit_freq_monthly"),
            InlineKeyboardButton("✏️ Другое...",     callback_data="rec_edit_freq_custom"),
        ],
    ])


# ---------------------------------------------------------------------------
# Главный экран: список правил
# ---------------------------------------------------------------------------

async def recurring_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Показывает экран «Постоянные расходы» со списком всех правил.
    Вызывается по кнопке «🔁 Постоянные» в главном меню.
    """
    user_id = str(update.effective_user.id)
    project_id = context.user_data.get('active_project_id')

    log_event(logger, "recurring_menu_opened", user_id=user_id, project_id=project_id)

    rules = await rec_utils.get_rules_for_user(user_id, project_id)
    text, keyboard = _build_rules_message_and_keyboard(rules)

    await update.message.reply_text(
        text,
        reply_markup=keyboard,
        parse_mode="Markdown",
    )


# ---------------------------------------------------------------------------
# ConversationHandler: добавление правила
# ---------------------------------------------------------------------------

async def rec_add_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Точка входа в диалог добавления постоянного расхода.
    Срабатывает на callback_data='rec_add'.
    """
    query = update.callback_query
    await query.answer()
    user_id = str(update.effective_user.id)
    project_id = context.user_data.get('active_project_id')

    # Проверяем права: владелец или редактор проекта
    if project_id is not None:
        from utils.permissions import Permission, has_permission
        if not await has_permission(update.effective_user.id, project_id, Permission.ADD_EXPENSE):
            await query.edit_message_text("❌ У тебя нет прав для добавления расходов в этом проекте.")
            return ConversationHandler.END

    # Очищаем предыдущие данные диалога
    for key in ['rec_amount', 'rec_category_id', 'rec_category_name', 'rec_comment']:
        context.user_data.pop(key, None)

    # Сохраняем user_id в контексте для использования в _finalize_rule
    context.user_data['rec_user_id'] = user_id
    log_event(logger, "rec_add_started", user_id=user_id)

    await query.edit_message_text(
        "➕ *Добавить постоянный расход*\n\n"
        "Введи сумму расхода:",
        parse_mode="Markdown",
    )
    return REC_ENTERING_AMOUNT


async def rec_handle_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обрабатывает ввод суммы. Показывает клавиатуру категорий."""
    user_id = str(update.effective_user.id)
    text = update.message.text.strip().replace(',', '.')

    try:
        amount = float(text)
        if amount <= 0:
            await update.message.reply_text(
                "❌ Сумма должна быть больше нуля. Попробуй ещё раз:"
            )
            return REC_ENTERING_AMOUNT
    except ValueError:
        await update.message.reply_text(
            "❌ Не понял сумму. Введи число, например: 500 или 9.99"
        )
        return REC_ENTERING_AMOUNT

    context.user_data['rec_amount'] = amount
    project_id = context.user_data.get('active_project_id')

    # Загружаем категории пользователя
    cats = await cat_utils.get_categories_for_user_project(user_id, project_id)
    if not cats:
        await update.message.reply_text(
            "❌ Нет доступных категорий. Сначала создай категорию.",
            reply_markup=get_main_menu_keyboard(),
        )
        return ConversationHandler.END

    keyboard = _build_category_keyboard(cats)
    await update.message.reply_text(
        f"💰 Сумма: *{amount}*\n\nВыбери категорию:",
        reply_markup=keyboard,
        parse_mode="Markdown",
    )
    return REC_CHOOSING_CATEGORY


async def rec_handle_category(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обрабатывает выбор категории. Запрашивает комментарий."""
    query = update.callback_query
    await query.answer()

    # Формат: cat_rec_{category_id}
    category_id = int(query.data.split('_')[2])
    user_id = str(update.effective_user.id)
    project_id = context.user_data.get('active_project_id')

    # Проверяем категорию
    cat = await cat_utils.get_category_by_id(user_id, category_id)
    if not cat and project_id is not None:
        from utils.categories import get_category_by_id_only
        cat = await get_category_by_id_only(category_id)
    if not cat:
        await query.edit_message_text("❌ Категория не найдена. Попробуй ещё раз.")
        return ConversationHandler.END

    context.user_data['rec_category_id'] = category_id
    context.user_data['rec_category_name'] = cat['name']

    emoji = config.DEFAULT_CATEGORIES.get(cat['name'], '📦')
    amount = context.user_data.get('rec_amount')

    await query.edit_message_text(
        f"💰 Сумма: *{amount}*\n"
        f"{emoji} Категория: *{cat['name']}*\n\n"
        "Введи комментарий к расходу\n"
        "(комментарий обязателен):",
        parse_mode="Markdown",
    )
    return REC_ENTERING_COMMENT


async def rec_handle_comment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Обрабатывает ввод комментария.
    Показывает клавиатуру выбора частоты.
    """
    text = update.message.text
    comment = text.strip()
    if not comment:
        await update.message.reply_text(
            "❌ Комментарий обязателен. Введи текст комментария:"
        )
        return REC_ENTERING_COMMENT

    context.user_data['rec_comment'] = comment

    amount = context.user_data.get('rec_amount')
    cat_name = context.user_data.get('rec_category_name', '')

    await update.message.reply_text(
        f"💰 {amount} — {cat_name}"
        + (f"\n📝 {comment}" if comment else '')
        + "\n\nВыбери, как часто списывать этот расход:",
        reply_markup=_build_frequency_keyboard(),
        parse_mode="Markdown",
    )
    return REC_CHOOSING_FREQUENCY


async def rec_handle_frequency_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Обрабатывает выбор базовой частоты (день/неделя/месяц/другое).
    При выборе «Другое...» переходит в состояние ввода произвольной частоты.
    """
    query = update.callback_query
    await query.answer()

    cb = query.data  # rec_freq_daily / rec_freq_weekly / rec_freq_monthly / rec_freq_custom

    if cb == 'rec_freq_custom':
        await query.edit_message_text(
            "✏️ Введи частоту в свободной форме:\n\n"
            "Примеры:\n"
            "• каждые 3 дня\n"
            "• каждые 2 недели\n"
            "• каждые 3 месяца\n"
            "• 15 числа\n"
            "• последний день месяца"
        )
        return REC_ENTERING_CUSTOM_FREQUENCY

    freq_map = {
        'rec_freq_daily':   {'frequency_type': 'daily'},
        'rec_freq_weekly':  {'frequency_type': 'weekly'},
        'rec_freq_monthly': {'frequency_type': 'monthly'},
    }
    freq_params = freq_map.get(cb)
    if not freq_params:
        await query.edit_message_text("❌ Неизвестный вариант. Попробуй ещё раз.")
        return REC_CHOOSING_FREQUENCY

    context.user_data['rec_freq_params'] = freq_params
    return await _finalize_rule(query, context)


async def rec_handle_custom_frequency(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Парсит произвольный текст частоты.
    При ошибке просит ввести снова с примерами.
    При успехе создаёт правило.
    """
    text = update.message.text.strip()
    freq_params = pd_utils.parse_custom_frequency(text)

    if freq_params is None:
        await update.message.reply_text(
            "❌ Не смог распознать частоту.\n\n"
            "Попробуй написать иначе, например:\n"
            "• каждые 3 дня\n"
            "• каждые 2 недели\n"
            "• каждые 3 месяца\n"
            "• каждый день\n"
            "• каждый месяц\n"
            "• 15 числа\n"
            "• последний день месяца"
        )
        return REC_ENTERING_CUSTOM_FREQUENCY

    context.user_data['rec_freq_params'] = freq_params
    return await _finalize_rule(update.message, context)


async def _finalize_rule(
    message_or_query,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    """
    Создаёт правило в БД и отправляет подтверждение.
    Общая точка выхода для rec_handle_frequency_choice и rec_handle_custom_frequency.

    Аргументы:
        message_or_query: объект Message или CallbackQuery (для редактирования/отправки)
    """
    # user_id сохранён при старте диалога в rec_add_start
    user_id = context.user_data.get('rec_user_id', '')

    project_id = context.user_data.get('active_project_id')
    amount = context.user_data.get('rec_amount')
    category_id = context.user_data.get('rec_category_id')
    cat_name = context.user_data.get('rec_category_name', '')
    comment = context.user_data.get('rec_comment', '')
    freq_params = context.user_data.get('rec_freq_params', {})

    today = datetime.date.today()

    rule_id = await rec_utils.create_rule(
        user_id=user_id,
        amount=amount,
        category_id=category_id,
        comment=comment,
        project_id=project_id,
        frequency_type=freq_params.get('frequency_type', 'monthly'),
        interval_value=freq_params.get('interval_value'),
        weekday=freq_params.get('weekday'),
        day_of_month=freq_params.get('day_of_month'),
        is_last_day_of_month=freq_params.get('is_last_day_of_month', False),
        start_date=today,
    )

    # Очищаем данные диалога
    for key in ['rec_amount', 'rec_category_id', 'rec_category_name',
                'rec_comment', 'rec_freq_params', 'rec_user_id']:
        context.user_data.pop(key, None)

    if rule_id is None:
        text = "❌ Не удалось создать постоянный расход. Попробуй позже."
    else:
        # Загружаем только что созданное правило для красивого отображения
        rule = await rec_utils.get_rule_by_id(rule_id, user_id)
        freq_text = rec_utils.format_frequency(rule) if rule else freq_params.get('frequency_type', '')
        next_run = _format_next_run(rule.get('next_run_at') if rule else None)

        display_name = comment or cat_name
        text = (
            f"✅ Постоянный расход добавлен!\nТакже расход внесен в базу!\n"
            f"💰 {amount} — {display_name}\n"
            f"📅 {freq_text}\n"
            f"🗓 Следующее списание: {next_run}"
        )
        log_event(logger, "rec_rule_created_via_dialog",
                  user_id=user_id, rule_id=rule_id, freq=freq_text)

    # Отправляем подтверждение
    if hasattr(message_or_query, 'edit_message_text'):
        # CallbackQuery
        await message_or_query.edit_message_text(text)
        # Дополнительно отправляем сообщение с главным меню
        await message_or_query.message.reply_text(
            "Возврат в главное меню.",
            reply_markup=get_main_menu_keyboard(),
        )
    else:
        # Message
        await message_or_query.reply_text(text, reply_markup=get_main_menu_keyboard())

    return ConversationHandler.END


async def rec_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Отменяет диалог добавления постоянного расхода."""
    for key in ['rec_amount', 'rec_category_id', 'rec_category_name',
                'rec_comment', 'rec_freq_params', 'rec_user_id']:
        context.user_data.pop(key, None)

    await update.message.reply_text(
        "Добавление отменено.",
        reply_markup=get_main_menu_keyboard(),
    )
    return ConversationHandler.END


# ---------------------------------------------------------------------------
# ConversationHandler: редактирование расписания правила
# ---------------------------------------------------------------------------

async def rec_edit_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Точка входа в редактирование частоты правила.
    callback_data = 'rec_edit_{id}'.
    """
    query = update.callback_query
    await query.answer()

    user_id = str(update.effective_user.id)
    rule_id = int(query.data.split('_')[2])

    rule = await rec_utils.get_rule_by_id(rule_id, user_id)
    if not rule:
        await query.answer("Правило не найдено.", show_alert=True)
        return ConversationHandler.END

    context.user_data['rec_edit_rule_id'] = rule_id
    context.user_data['rec_edit_user_id'] = user_id

    await query.edit_message_text(
        f"✏️ Изменить расписание\n\n"
        f"Текущее: {rec_utils.format_frequency(rule)}\n\n"
        f"Выбери новую частоту:",
        reply_markup=_build_edit_frequency_keyboard(),
    )
    return REC_EDIT_CHOOSING_FREQUENCY


async def rec_edit_frequency_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Обрабатывает выбор базовой частоты при редактировании правила.
    """
    query = update.callback_query
    await query.answer()

    cb = query.data
    if cb == 'rec_edit_freq_custom':
        await query.edit_message_text(
            "✏️ Введи новую частоту в свободной форме:\n\n"
            "Примеры:\n"
            "• каждые 3 дня\n"
            "• каждые 2 недели\n"
            "• каждые 3 месяца\n"
            "• 15 числа\n"
            "• последний день месяца"
        )
        return REC_EDIT_ENTERING_CUSTOM_FREQUENCY

    freq_map = {
        'rec_edit_freq_daily':   {'frequency_type': 'daily'},
        'rec_edit_freq_weekly':  {'frequency_type': 'weekly'},
        'rec_edit_freq_monthly': {'frequency_type': 'monthly'},
    }
    freq_params = freq_map.get(cb)
    if not freq_params:
        await query.edit_message_text("❌ Неизвестный вариант. Попробуй ещё раз.")
        return REC_EDIT_CHOOSING_FREQUENCY

    return await _finalize_rule_schedule_edit(query, context, freq_params)


async def rec_edit_custom_frequency(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Парсит пользовательский ввод частоты для редактирования правила.
    """
    text = update.message.text.strip()
    freq_params = pd_utils.parse_custom_frequency(text)

    if freq_params is None:
        await update.message.reply_text(
            "❌ Не смог распознать частоту.\n\n"
            "Попробуй написать иначе, например:\n"
            "• каждые 3 дня\n"
            "• каждые 2 недели\n"
            "• каждые 3 месяца\n"
            "• каждый день\n"
            "• каждый месяц\n"
            "• 15 числа\n"
            "• последний день месяца"
        )
        return REC_EDIT_ENTERING_CUSTOM_FREQUENCY

    return await _finalize_rule_schedule_edit(update.message, context, freq_params)


async def _finalize_rule_schedule_edit(message_or_query, context: ContextTypes.DEFAULT_TYPE, freq_params: dict) -> int:
    """
    Сохраняет новое расписание правила и отправляет пользователю подтверждение.
    """
    user_id = context.user_data.get('rec_edit_user_id', '')
    rule_id = context.user_data.get('rec_edit_rule_id')

    if not user_id or not rule_id:
        err_text = "❌ Не удалось определить правило для редактирования."
        if hasattr(message_or_query, 'edit_message_text'):
            await message_or_query.edit_message_text(err_text)
        else:
            await message_or_query.reply_text(err_text, reply_markup=get_main_menu_keyboard())
        return ConversationHandler.END

    next_run = await rec_utils.update_rule_schedule(
        rule_id=rule_id,
        user_id=user_id,
        frequency_type=freq_params.get('frequency_type', 'monthly'),
        interval_value=freq_params.get('interval_value'),
        weekday=freq_params.get('weekday'),
        day_of_month=freq_params.get('day_of_month'),
        is_last_day_of_month=freq_params.get('is_last_day_of_month', False),
    )

    context.user_data.pop('rec_edit_rule_id', None)
    context.user_data.pop('rec_edit_user_id', None)

    if next_run is None:
        text = "❌ Не удалось обновить расписание. Попробуй позже."
    else:
        rule = await rec_utils.get_rule_by_id(rule_id, user_id)
        freq_text = rec_utils.format_frequency(rule) if rule else _freq_display(freq_params)
        text = (
            f"✅ Расписание обновлено!\n\n"
            f"📅 {freq_text}\n"
            f"🗓 Следующее списание: {_format_next_run(next_run)}"
        )

    if hasattr(message_or_query, 'edit_message_text'):
        await message_or_query.edit_message_text(text)
        await message_or_query.message.reply_text(
            "Возврат в главное меню.",
            reply_markup=get_main_menu_keyboard(),
        )
    else:
        await message_or_query.reply_text(text, reply_markup=get_main_menu_keyboard())

    return ConversationHandler.END


# ---------------------------------------------------------------------------
# Inline action handlers: пауза / возобновление / удаление
# ---------------------------------------------------------------------------

async def rec_pause_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Приостанавливает правило. callback_data = 'rec_pause_{id}'."""
    query = update.callback_query
    await query.answer()
    user_id = str(update.effective_user.id)
    rule_id = int(query.data.split('_')[2])

    success = await rec_utils.pause_rule(rule_id, user_id)
    if not success:
        await query.answer("Правило не найдено или уже на паузе.", show_alert=True)
        return

    # Обновляем список
    project_id = context.user_data.get('active_project_id')
    rules = await rec_utils.get_rules_for_user(user_id, project_id)
    text, keyboard = _build_rules_message_and_keyboard(rules)
    await query.edit_message_text(text, reply_markup=keyboard, parse_mode="Markdown")


async def rec_resume_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Возобновляет правило. callback_data = 'rec_resume_{id}'."""
    query = update.callback_query
    await query.answer()
    user_id = str(update.effective_user.id)
    rule_id = int(query.data.split('_')[2])

    success = await rec_utils.resume_rule(rule_id, user_id)
    if not success:
        await query.answer("Правило не найдено или уже активно.", show_alert=True)
        return

    project_id = context.user_data.get('active_project_id')
    rules = await rec_utils.get_rules_for_user(user_id, project_id)
    text, keyboard = _build_rules_message_and_keyboard(rules)
    await query.edit_message_text(text, reply_markup=keyboard, parse_mode="Markdown")


async def rec_delete_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Запрашивает подтверждение удаления. callback_data = 'rec_delete_{id}'.
    Показывает кнопки [✅ Да, удалить] [❌ Отмена].
    """
    query = update.callback_query
    await query.answer()
    user_id = str(update.effective_user.id)
    rule_id = int(query.data.split('_')[2])

    rule = await rec_utils.get_rule_by_id(rule_id, user_id)
    if not rule:
        await query.answer("Правило не найдено.", show_alert=True)
        return

    display_name = rule.get('comment') or rule.get('category_name', '')
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Да, удалить", callback_data=f"rec_delete_confirm_{rule_id}"),
        InlineKeyboardButton("❌ Отмена",      callback_data="rec_delete_cancel"),
    ]])
    await query.edit_message_text(
        f"Удалить постоянный расход?\n\n"
        f"💰 {rule['amount']} — {display_name}\n"
        f"📅 {rec_utils.format_frequency(rule)}",
        reply_markup=keyboard,
    )


async def rec_delete_confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Подтверждает удаление. callback_data = 'rec_delete_confirm_{id}'."""
    query = update.callback_query
    await query.answer()
    user_id = str(update.effective_user.id)
    rule_id = int(query.data.split('_')[3])

    success = await rec_utils.delete_rule(rule_id, user_id)
    if not success:
        await query.answer("Не удалось удалить правило.", show_alert=True)
        return

    project_id = context.user_data.get('active_project_id')
    rules = await rec_utils.get_rules_for_user(user_id, project_id)
    text, keyboard = _build_rules_message_and_keyboard(rules)
    await query.edit_message_text(text, reply_markup=keyboard, parse_mode="Markdown")


async def rec_delete_cancel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Отменяет удаление — возвращает к списку."""
    query = update.callback_query
    await query.answer()
    user_id = str(update.effective_user.id)
    project_id = context.user_data.get('active_project_id')

    rules = await rec_utils.get_rules_for_user(user_id, project_id)
    text, keyboard = _build_rules_message_and_keyboard(rules)
    await query.edit_message_text(text, reply_markup=keyboard, parse_mode="Markdown")


async def rec_row_label_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Пустой обработчик для визуального label-кнопки вида '1:'."""
    query = update.callback_query
    await query.answer()


# ---------------------------------------------------------------------------
# Pattern suggestion
# ---------------------------------------------------------------------------

async def suggest_recurring_if_pattern(
    bot,
    user_id: str,
    project_id: Optional[int],
    category_id: int,
    comment: str,
    bot_data: dict,
) -> None:
    """
    Проверяет историю расходов на наличие паттерна и предлагает создать постоянный расход.
    Вызывается неблокирующим образом из handlers/expense.py через asyncio.create_task().

    Условия для предложения:
    1. Cooldown не активен (прошло > 7 дней с последнего предложения)
    2. Нет активного recurring-правила для этой же комбинации (category + comment)
    3. Обнаружен паттерн (≥ 3 транзакции с похожими суммами и интервалами)

    Если все условия выполнены — отправляет сообщение с кнопками «Да» / «Нет».
    """
    if not comment or not comment.strip():
        return

    # 1. Проверка cooldown
    if pd_utils.is_on_cooldown(bot_data, user_id, comment):
        return

    # 2. Проверка — нет ли уже активного правила для этого паттерна
    try:
        from utils import db
        norm = pd_utils.normalize_comment(comment)
        existing_rule = await db.fetchval(
            """
            SELECT 1 FROM recurring_rules
            WHERE user_id = $1
              AND category_id = $2
              AND LOWER(TRIM(comment)) = $3
              AND status = 'active'
            LIMIT 1
            """,
            user_id, category_id, norm,
        )
        if existing_rule:
            return
    except Exception:
        return

    # 3. Обнаружение паттерна
    pattern = await pd_utils.detect_pattern_for_user(
        user_id=user_id,
        project_id=project_id,
        category_id=category_id,
        comment=comment,
    )
    if pattern is None:
        return

    # Сохраняем паттерн в кэше для обработчика «Да»
    pd_utils.save_pattern_to_cache(bot_data, user_id, pattern)

    # Формируем сообщение
    freq_text = _freq_display(pattern)
    ch = pd_utils.comment_hash(comment)
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton(
            "✅ Да",
            callback_data=f"rec_suggest_yes_{category_id}_{ch}",
        ),
        InlineKeyboardButton(
            "❌ Нет",
            callback_data=f"rec_suggest_no_{user_id}_{ch}",
        ),
    ]])

    try:
        await bot.send_message(
            chat_id=user_id,
            text=(
                f"💡 Замечен регулярный расход:\n"
                f"💰 {pattern['amount']} — {comment}\n"
                f"📅 ~{freq_text}\n\n"
                "Сделать постоянным расходом?"
            ),
            reply_markup=keyboard,
        )
        log_event(logger, "rec_pattern_suggested",
                  user_id=user_id, category_id=category_id, comment=comment)
    except Exception as e:
        log_error(logger, e, "rec_suggest_send_error", user_id=user_id)


def _freq_display(pattern: dict) -> str:
    """Человекочитаемое описание частоты для сообщения-предложения."""
    freq = pattern.get('frequency_type', '')
    n = pattern.get('interval_value')
    if freq == 'daily':
        return "каждый день"
    if freq == 'weekly':
        return "каждую неделю"
    if freq == 'monthly':
        return "каждый месяц"
    if freq == 'every_n_days' and n:
        return f"каждые {n} дн."
    if freq == 'every_n_weeks' and n:
        return f"каждые {n} нед."
    if freq == 'every_n_months' and n:
        return f"каждые {n} мес."
    return freq


async def rec_suggest_yes_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Пользователь согласился создать постоянный расход по предложению паттерна.
    callback_data = 'rec_suggest_yes_{category_id}_{comment_hash}'

    Для надёжности повторно запускает detect_pattern_for_user (работает после рестарта бота).
    Если паттерн уже не актуален — сообщает об этом.
    """
    query = update.callback_query
    await query.answer()
    user_id = str(update.effective_user.id)
    project_id = context.user_data.get('active_project_id')

    parts = query.data.split('_')
    # rec_suggest_yes_{category_id}_{comment_hash}
    category_id = int(parts[3])
    ch = parts[4]

    # Сначала пробуем кэш, иначе переобнаружим паттерн по category_id
    bot_data = context.bot_data
    pattern = None

    # Ищем паттерн в кэше (перебираем все сохранённые для этого пользователя)
    patterns_cache = bot_data.get('rec_patterns', {})
    for key, cached_pattern in patterns_cache.items():
        if (key.startswith(user_id + '_') and
                cached_pattern.get('category_id') == category_id and
                pd_utils.comment_hash(cached_pattern.get('comment', '')) == ch):
            pattern = cached_pattern
            break

    if pattern is None:
        await query.edit_message_text(
            "Не смог восстановить данные паттерна. "
            "Попробуй добавить постоянный расход вручную через меню 🔁 Авторасходы."
        )
        return

    # Создаём правило
    today = datetime.date.today()
    rule_id = await rec_utils.create_rule(
        user_id=user_id,
        amount=pattern['amount'],
        category_id=pattern['category_id'],
        comment=pattern['comment'],
        project_id=project_id,
        frequency_type=pattern['frequency_type'],
        interval_value=pattern.get('interval_value'),
        weekday=None,
        day_of_month=None,
        is_last_day_of_month=False,
        start_date=today,
    )

    # Устанавливаем cooldown чтобы не предлагать снова
    pd_utils.set_cooldown(bot_data, user_id, pattern['comment'])

    if rule_id:
        rule = await rec_utils.get_rule_by_id(rule_id, user_id)
        freq_text = rec_utils.format_frequency(rule) if rule else _freq_display(pattern)
        await query.edit_message_text(
            f"✅ Постоянный расход создан!\n\n"
            f"💰 {pattern['amount']} — {pattern['comment']}\n"
            f"📅 {freq_text}"
        )
        log_event(logger, "rec_rule_created_via_suggest",
                  user_id=user_id, rule_id=rule_id)
    else:
        await query.edit_message_text("❌ Не удалось создать постоянный расход. Попробуй позже.")


async def rec_suggest_no_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Пользователь отказался от создания постоянного расхода.
    callback_data = 'rec_suggest_no_{user_id}_{comment_hash}'
    Записывает cooldown и убирает сообщение-предложение.
    """
    query = update.callback_query
    await query.answer()

    parts = query.data.split('_')
    # rec_suggest_no_{user_id}_{comment_hash}
    target_user_id = parts[3]
    ch = parts[4]

    # Ищем комментарий в кэше для cooldown
    bot_data = context.bot_data
    patterns_cache = bot_data.get('rec_patterns', {})
    comment_for_cooldown = None
    for key, cached_pattern in patterns_cache.items():
        if (key.startswith(target_user_id + '_') and
                pd_utils.comment_hash(cached_pattern.get('comment', '')) == ch):
            comment_for_cooldown = cached_pattern.get('comment', '')
            break

    if comment_for_cooldown:
        pd_utils.set_cooldown(bot_data, target_user_id, comment_for_cooldown)

    await query.edit_message_text(
        "Понял, не буду предлагать ещё 7 дней. 👍"
    )
    log_event(logger, "rec_suggest_declined", user_id=target_user_id)


# ---------------------------------------------------------------------------
# Регистрация обработчиков
# ---------------------------------------------------------------------------

def register_recurring_handlers(application) -> None:
    """
    Регистрирует все обработчики постоянных расходов.
    Должна вызываться ДО register_expense_handlers (expense ловит любой текст).
    """

    # ConversationHandler для добавления правила
    add_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(rec_add_start, pattern=r'^rec_add$'),
        ],
        states={
            REC_ENTERING_AMOUNT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, rec_handle_amount),
            ],
            REC_CHOOSING_CATEGORY: [
                CallbackQueryHandler(rec_handle_category, pattern=r'^cat_rec_\d+$'),
            ],
            REC_ENTERING_COMMENT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, rec_handle_comment),
            ],
            REC_CHOOSING_FREQUENCY: [
                CallbackQueryHandler(rec_handle_frequency_choice, pattern=r'^rec_freq_'),
            ],
            REC_ENTERING_CUSTOM_FREQUENCY: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, rec_handle_custom_frequency),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", rec_cancel),
            MessageHandler(
                filters.Regex(main_menu_button_regex("main_menu")),
                rec_cancel,
            ),
        ],
        name="add_recurring_conversation",
        persistent=False,
    )
    application.add_handler(add_conv)

    # ConversationHandler для редактирования расписания
    edit_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(rec_edit_start, pattern=r'^rec_edit_\d+$'),
        ],
        states={
            REC_EDIT_CHOOSING_FREQUENCY: [
                CallbackQueryHandler(rec_edit_frequency_choice, pattern=r'^rec_edit_freq_'),
            ],
            REC_EDIT_ENTERING_CUSTOM_FREQUENCY: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, rec_edit_custom_frequency),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", rec_cancel),
            MessageHandler(
                filters.Regex(main_menu_button_regex("main_menu")),
                rec_cancel,
            ),
        ],
        name="edit_recurring_conversation",
        persistent=False,
    )
    application.add_handler(edit_conv)

    # Главный экран (кнопка в меню)
    application.add_handler(MessageHandler(
        filters.Regex(main_menu_button_regex("recurring")),
        recurring_menu,
    ))

    # Inline-действия: пауза / возобновление / удаление
    application.add_handler(CallbackQueryHandler(
        rec_row_label_callback,      pattern=r'^rec_row_label_\d+$'))
    application.add_handler(CallbackQueryHandler(
        rec_pause_callback,          pattern=r'^rec_pause_\d+$'))
    application.add_handler(CallbackQueryHandler(
        rec_resume_callback,         pattern=r'^rec_resume_\d+$'))
    application.add_handler(CallbackQueryHandler(
        rec_delete_callback,         pattern=r'^rec_delete_\d+$'))
    application.add_handler(CallbackQueryHandler(
        rec_delete_confirm_callback, pattern=r'^rec_delete_confirm_\d+$'))
    application.add_handler(CallbackQueryHandler(
        rec_delete_cancel_callback,  pattern=r'^rec_delete_cancel$'))

    # Pattern suggestion callbacks
    application.add_handler(CallbackQueryHandler(
        rec_suggest_yes_callback, pattern=r'^rec_suggest_yes_\d+_[0-9a-f]+$'))
    application.add_handler(CallbackQueryHandler(
        rec_suggest_no_callback,  pattern=r'^rec_suggest_no_\S+$'))
