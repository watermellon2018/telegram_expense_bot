"""
Обработчики команд для работы с проектами
"""

import time

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from handlers.currency import currency_keyboard
from utils import currencies, helpers, projects
from utils.currency_reporting import format_project_totals
from utils.helpers import project_menu_button_regex
from utils.logger import get_logger, log_command, log_error, log_event

logger = get_logger("handlers.project")

# Состояния для ConversationHandler
(
    CONFIRMING_DELETE,
    ENTERING_PROJECT_NAME,
    ENTERING_PROJECT_TO_DELETE,
    CHOOSING_PROJECT_TO_DELETE,
    CHOOSING_TEMPLATE,
    CHOOSING_REPORT_CURRENCY,
    CHOOSING_INPUT_CURRENCY,
    ENTERING_FALLBACK_RATE,
) = range(8)


async def project_create_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    parts = update.message.text.split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        return await button_project_create_start(update, context)
    context.user_data['new_project_name'] = parts[1].strip()
    context.user_data['new_project_template'] = None
    await update.message.reply_text("Выберите валюту отчётности проекта:", reply_markup=currency_keyboard("proj_report_"))
    return CHOOSING_REPORT_CURRENCY


async def project_list_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Обрабатывает команду /project_list для отображения списка проектов
    """
    user_id = update.effective_user.id
    start_time = time.time()

    log_command(logger, "project_list", user_id=user_id)

    try:
        # Получаем список проектов
        all_projects = await projects.get_all_projects(user_id)

        if not all_projects:
            log_event(logger, "project_list_empty", user_id=user_id)
            await update.message.reply_text(
                "📋 У вас пока нет проектов.\n\n"
                "Создайте проект командой:\n"
                "/project_create <название>"
            )
            return

        # Получаем активный проект
        active_project = await projects.get_active_project(user_id)
        active_project_id = active_project['project_id'] if active_project else None

        # Формируем список
        message = "📋 Ваши проекты:\n\n"

        for project in all_projects:
            project_id = project['project_id']
            project_name = project['project_name']
            created_date = project['created_date']
            role = project.get('role', 'owner')
            is_owner = project.get('is_owner', False)

            # Получаем статистику по проекту
            stats = await projects.get_project_stats(user_id, project_id)

            # Получаем emoji роли
            from utils.permissions import get_role_description
            role_emoji = get_role_description(role)

            # Отмечаем активный проект
            if project_id == active_project_id:
                message += f"📁 *{project_name}* (активен)\n"
            else:
                message += f"📁 {project_name}\n"

            message += f"   {role_emoji}\n"
            message += f"   ID: {project_id}\n"
            message += f"   Создан: {created_date}\n"
            message += format_project_totals(stats) + "\n\n"

        # Показываем текущий режим
        if active_project_id is None:
            message += "📊 Текущий режим: Общие расходы"
        else:
            message += f"📁 Текущий режим: Проект '{active_project['project_name']}'"

        await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN)

        duration = time.time() - start_time
        log_event(logger, "project_list_success", user_id=user_id,
                 projects_count=len(all_projects), active_project_id=active_project_id, duration=duration)

    except Exception as e:
        duration = time.time() - start_time
        log_error(logger, e, "project_list_error", user_id=user_id, duration=duration)
        await update.message.reply_text("❌ Произошла ошибка при получении списка проектов.")


async def project_select_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Обрабатывает команду /project_select для переключения на проект
    Если параметр не указан, показывает список проектов для выбора
    """
    user_id = update.effective_user.id
    message_text = update.message.text

    # Проверяем, содержит ли команда название или ID проекта
    parts = message_text.split(maxsplit=1)

    if len(parts) < 2:
        # Показываем список проектов для выбора
        await show_project_selection_menu(update, context)
        return

    project_identifier = parts[1].strip()

    # Пытаемся найти проект по ID или названию
    project = None

    # Проверяем, является ли идентификатор числом (ID)
    if project_identifier.isdigit():
        project = await projects.get_project_by_id(user_id, int(project_identifier))

    # Если не нашли по ID, ищем по названию
    if project is None:
        project = await projects.get_project_by_name(user_id, project_identifier)

    if project is None:
        await update.message.reply_text(
            f"❌ Проект '{project_identifier}' не найден.\n\n"
            f"Посмотрите список проектов: /project_list"
        )
        return

    # Переключаемся на проект
    result = await projects.set_active_project(user_id, project['project_id'])

    if result['success']:
        # Сохраняем в контексте пользователя
        context.user_data['active_project_id'] = project['project_id']

        await update.message.reply_text(
            f"✅ {result['message']}\n\n"
            f"Теперь все расходы будут записываться в проект '{project['project_name']}'."
        )
    else:
        await update.message.reply_text(f"❌ {result['message']}")


async def project_main_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Обрабатывает команду /project_main для переключения на общие расходы
    """
    from utils.helpers import get_main_menu_keyboard

    user_id = update.effective_user.id

    # Переключаемся на общие расходы
    result = await projects.set_active_project(user_id, None)

    if result['success']:
        # Сбрасываем в контексте пользователя
        context.user_data['active_project_id'] = None

        await update.message.reply_text(
            f"✅ {result['message']}\n\n"
            f"Теперь все расходы будут записываться в общие расходы.",
            reply_markup=get_main_menu_keyboard()
        )
    else:
        await update.message.reply_text(
            f"❌ {result['message']}",
            reply_markup=get_main_menu_keyboard()
        )


async def _show_delete_menu(update: Update, context) -> int:
    """
    Вспомогательная функция: показывает инлайн-меню с проектами,
    которые пользователь может удалить (только собственные — роль owner).
    """
    from utils.permissions import Permission, has_permission

    user_id = update.effective_user.id
    all_projects = await projects.get_all_projects(user_id)

    # Оставляем только те проекты, для которых есть право DELETE_PROJECT
    deletable = []
    for p in all_projects:
        if await has_permission(user_id, p['project_id'], Permission.DELETE_PROJECT):
            deletable.append(p)

    if not deletable:
        await update.message.reply_text(
            "📋 Нет проектов, доступных для удаления.\n\n"
            "Удалить можно только собственные проекты (роль «Владелец»)."
        )
        return ConversationHandler.END

    # Формируем инлайн-клавиатуру
    keyboard = []
    for p in deletable:
        keyboard.append([InlineKeyboardButton(
            f"🗑 {p['project_name']}",
            callback_data=f"del_proj_{p['project_id']}"
        )])
    keyboard.append([InlineKeyboardButton("❌ Отмена", callback_data="del_proj_cancel")])
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "🗑 Выберите проект для удаления:\n\n"
        "Проект будет деактивирован. Данные будут храниться в базе месяц.",
        reply_markup=reply_markup
    )
    return CHOOSING_PROJECT_TO_DELETE


async def project_delete_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Вход через команду /project_delete — показывает инлайн-меню с выбором проекта.
    """
    return await _show_delete_menu(update, context)


async def project_delete_choose_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Обрабатывает выбор проекта из инлайн-меню удаления.
    Показывает карточку проекта с кнопками «Подтвердить удаление» / «Отмена».
    """
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id

    if query.data == "del_proj_cancel":
        await query.edit_message_text("Удаление проекта отменено.")
        return ConversationHandler.END

    try:
        project_id = int(query.data.split("_")[-1])
    except (ValueError, IndexError):
        await query.edit_message_text("❌ Ошибка выбора проекта.")
        return ConversationHandler.END

    project = await projects.get_project_by_id(user_id, project_id)
    if not project:
        await query.edit_message_text("❌ Проект не найден или у вас нет доступа.")
        return ConversationHandler.END

    # Сохраняем в контексте для шага подтверждения
    context.user_data['delete_project_id'] = project_id
    context.user_data['delete_project_name'] = project['project_name']

    stats = await projects.get_project_stats(user_id, project_id)

    keyboard = [
        [InlineKeyboardButton("✅ Да, удалить", callback_data=f"del_confirm_{project_id}")],
        [InlineKeyboardButton("❌ Отмена", callback_data="del_proj_cancel")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        f"⚠️ Удалить проект «{project['project_name']}»?\n\n"
        f"📊 {format_project_totals(stats)}\n\n"
        f"Проект будет деактивирован. Данные будут храниться в базе месяц.",
        reply_markup=reply_markup
    )
    return CONFIRMING_DELETE


async def project_delete_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Финальное подтверждение удаления — обрабатывает callback «Да, удалить».
    """
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id

    if query.data == "del_proj_cancel":
        context.user_data.pop('delete_project_id', None)
        context.user_data.pop('delete_project_name', None)
        await query.edit_message_text("Удаление проекта отменено.")
        return ConversationHandler.END

    try:
        project_id = int(query.data.split("_")[-1])
    except (ValueError, IndexError):
        await query.edit_message_text("❌ Ошибка подтверждения.")
        return ConversationHandler.END

    result = await projects.delete_project(user_id, project_id)

    context.user_data.pop('delete_project_id', None)
    context.user_data.pop('delete_project_name', None)

    if result['success']:
        # Определяем, был ли удалённый проект активным у пользователя
        was_active = context.user_data.get('active_project_id') == project_id
        if was_active:
            context.user_data['active_project_id'] = None
            status_line = "Вы переключены на общие расходы."
        else:
            active_id = context.user_data.get('active_project_id')
            if active_id:
                active = await projects.get_project_by_id(user_id, active_id)
                project_name = active['project_name'] if active else None
            else:
                project_name = None

            if project_name:
                status_line = f"Активный проект не изменился: «{project_name}»."
            else:
                status_line = "Вы находитесь в режиме общих расходов."

        await query.edit_message_text(
            f"✅ {result['message']}\n\n{status_line}"
        )
    else:
        await query.edit_message_text(f"❌ {result['message']}")

    return ConversationHandler.END


async def button_project_delete_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Вход через кнопку меню — показывает инлайн-меню с выбором проекта.
    """
    return await _show_delete_menu(update, context)




async def button_project_create_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Начинает создание проекта для кнопки (просит название)
    """
    await update.message.reply_text(
        "🆕 Введите название нового проекта:"
    )
    return ENTERING_PROJECT_NAME


async def button_project_create_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Получает название проекта и предлагает выбрать шаблон категорий.

    Дубликат имени проверяем здесь, чтобы не вести пользователя через выбор
    шаблона впустую.
    """
    import config

    user_id = update.effective_user.id
    project_name = update.message.text.strip()

    if not project_name:
        await update.message.reply_text("❌ Название проекта не может быть пустым. Введите название:")
        return ENTERING_PROJECT_NAME

    # Ранняя проверка дубликата (финальная всё равно есть в create_project)
    existing = await projects.get_project_by_name(user_id, project_name)
    if existing:
        from utils.helpers import get_main_menu_keyboard
        await update.message.reply_text(
            f"❌ Проект '{project_name}' уже существует.",
            reply_markup=get_main_menu_keyboard()
        )
        return ConversationHandler.END

    context.user_data['new_project_name'] = project_name

    # Кнопки: «Обычный» + по одной на каждый тематический шаблон
    keyboard = [[InlineKeyboardButton("📋 Обычный (общие категории)", callback_data="tpl_none")]]
    for key, template in config.PROJECT_TEMPLATES.items():
        keyboard.append([InlineKeyboardButton(template["title"], callback_data=f"tpl_{key}")])
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        f"🆕 Проект «{project_name}».\n\n"
        "Выберите шаблон категорий:\n"
        "• «Обычный» — будут видны ваши общие категории.\n"
        "• Тематический — проект получит только свой набор категорий.",
        reply_markup=reply_markup
    )
    return CHOOSING_TEMPLATE


async def button_project_create_template(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer()
    raw = update.callback_query.data.removeprefix("tpl_")
    import config
    if not context.user_data.get('new_project_name') or (raw != "none" and raw not in config.PROJECT_TEMPLATES):
        await update.callback_query.edit_message_text("Сессия истекла. Начните создание проекта заново.")
        return ConversationHandler.END
    context.user_data['new_project_template'] = None if raw == "none" else raw
    await update.callback_query.edit_message_text("Выберите валюту отчётности проекта:", reply_markup=currency_keyboard("proj_report_"))
    return CHOOSING_REPORT_CURRENCY


async def project_report_currency(update, context):
    await update.callback_query.answer()
    try:
        code = currencies.normalize_currency(update.callback_query.data.removeprefix("proj_report_"))
    except currencies.CurrencyError as exc:
        await update.callback_query.edit_message_text(str(exc))
        return ConversationHandler.END
    context.user_data['new_project_reporting'] = code
    await update.callback_query.edit_message_text("В какой валюте вы будете вводить расходы по умолчанию?", reply_markup=currency_keyboard("proj_input_", default=code))
    return CHOOSING_INPUT_CURRENCY


async def project_input_currency(update, context):
    await update.callback_query.answer()
    try:
        code = currencies.normalize_currency(update.callback_query.data.removeprefix("proj_input_"))
        report = context.user_data['new_project_reporting']
    except (currencies.CurrencyError, KeyError):
        await update.callback_query.edit_message_text("Сессия истекла. Начните создание проекта заново.")
        return ConversationHandler.END
    context.user_data['new_project_input'] = code
    if code == report:
        return await finish_project_creation(update, context)
    await update.callback_query.edit_message_text(
        f"Задайте резервный курс: сколько {report} стоит 1 {code}?\n"
        "Он применяется, если автоматический курс недоступен. Введите число или /skip."
    )
    return ENTERING_FALLBACK_RATE


async def project_fallback_rate(update, context):
    try:
        rate = None if update.message.text == '/skip' else currencies.parse_amount(update.message.text)
    except currencies.CurrencyError as exc:
        await update.message.reply_text(f"{exc} Введите курс или /skip.")
        return ENTERING_FALLBACK_RATE
    return await finish_project_creation(update, context, rate)


async def finish_project_creation(update, context, rate=None):
    uid = update.effective_user.id
    name = context.user_data.get('new_project_name')
    report = context.user_data.get('new_project_reporting')
    source = context.user_data.get('new_project_input')
    reply = update.callback_query.edit_message_text if update.callback_query else update.message.reply_text
    if not all((name, report, source)):
        await reply("Сессия истекла. Начните создание проекта заново.")
        return ConversationHandler.END
    result = await projects.create_project(uid, name, context.user_data.get('new_project_template'),
                                          reporting_currency=report, input_currency=source, fallback_rate=rate)
    if result['success']:
        pid = result['project_id']
        selected = await projects.set_active_project(uid, pid)
        if selected.get('success'):
            context.user_data['active_project_id'] = pid
        await reply(f"✅ Проект «{name}» создан.\nВалюта отчётности: {report}\nВаша валюта ввода: {source}\nНастройки валют: /currency")
    else:
        await reply(f"❌ {result['message']}")
    for key in list(context.user_data):
        if key.startswith('new_project_'):
            context.user_data.pop(key, None)
    return ConversationHandler.END


async def button_project_select_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Начинает выбор проекта для кнопки (показывает список проектов)
    """
    await show_project_selection_menu(update, context)
    return ConversationHandler.END


async def show_project_selection_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Показывает меню выбора проекта с inline keyboard
    """
    user_id = update.effective_user.id

    # Получаем список всех доступных проектов
    all_projects = await projects.get_all_projects(user_id)

    if not all_projects:
        await update.message.reply_text(
            "📋 У вас пока нет проектов.\n\n"
            "Создайте проект командой:\n"
            "/project_create <название>"
        )
        return

    # Получаем активный проект
    active_project = await projects.get_active_project(user_id)
    active_project_id = active_project['project_id'] if active_project else None

    # Формируем inline keyboard с проектами
    keyboard = []

    # Группируем проекты по 2 в ряд
    for i in range(0, len(all_projects), 2):
        row = []
        for j in range(2):
            if i + j < len(all_projects):
                project = all_projects[i + j]
                project_id = project['project_id']
                project_name = project['project_name']

                # Отмечаем активный проект
                prefix = "✅ " if project_id == active_project_id else ""
                button_text = f"{prefix}{project_name}"

                # Ограничиваем длину текста кнопки (Telegram лимит ~64 символа)
                if len(button_text) > 60:
                    button_text = button_text[:57] + "..."

                row.append(InlineKeyboardButton(
                    button_text,
                    callback_data=f"select_proj_{project_id}"
                ))
        keyboard.append(row)

    # Добавляем кнопку для переключения на общие расходы
    if active_project_id is not None:
        keyboard.append([InlineKeyboardButton(
            "📊 Общие расходы",
            callback_data="select_proj_none"
        )])

    reply_markup = InlineKeyboardMarkup(keyboard)

    message = "🔄 Выберите проект:\n\n"
    if active_project_id is not None:
        message += f"Текущий активный проект: {active_project['project_name']}\n\n"
    else:
        message += "Текущий режим: Общие расходы\n\n"

    await update.message.reply_text(message, reply_markup=reply_markup)


async def handle_project_selection_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Обрабатывает выбор проекта через callback query
    """
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id
    callback_data = query.data

    # Извлекаем project_id из callback_data
    if callback_data == "select_proj_none":
        project_id = None
    else:
        try:
            project_id = int(callback_data.split("_")[-1])
        except (ValueError, IndexError):
            await query.edit_message_text("❌ Ошибка выбора проекта.")
            return

    # Переключаемся на проект
    if project_id is None:
        result = await projects.set_active_project(user_id, None)
        if result['success']:
            context.user_data['active_project_id'] = None
            await query.edit_message_text(
                f"✅ {result['message']}\n\n"
                f"Теперь все расходы будут записываться в общие расходы."
            )
        else:
            await query.edit_message_text(f"❌ {result['message']}")
    else:
        # Проверяем доступ к проекту
        project = await projects.get_project_by_id(user_id, project_id)
        if project is None:
            await query.edit_message_text(
                "❌ Проект не найден или у вас нет доступа к нему."
            )
            return

        result = await projects.set_active_project(user_id, project_id)
        if result['success']:
            context.user_data['active_project_id'] = project_id
            await query.edit_message_text(
                f"✅ {result['message']}\n\n"
                f"Теперь все расходы будут записываться в проект '{project['project_name']}'."
            )
        else:
            await query.edit_message_text(f"❌ {result['message']}")


async def project_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Общий отменитель для всех conversations
    """
    return await helpers.cancel_conversation(update, context, "Операция отменена.", clear_data=True)

async def project_info_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Обрабатывает команду /project_info для информации об активном проекте
    """
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    from utils.permissions import get_role_description

    user_id = update.effective_user.id
    active_project = await projects.get_active_project(user_id)

    if active_project is None:
        await update.message.reply_text(
            "📊 Текущий режим: Общие расходы\n\n"
            "Все расходы записываются в общую базу.\n\n"
            "Чтобы переключиться на проект, используйте:\n"
            "/project_select"
        )
        return

    # Получаем статистику по проекту
    stats = await projects.get_project_stats(user_id, active_project['project_id'])

    # Получаем количество участников
    members = await projects.get_project_members(active_project['project_id'])

    # Получаем роль и emoji
    role = active_project.get('role', 'owner')
    role_emoji = get_role_description(role)

    message = f"📁 Текущий проект: {active_project['project_name']}\n\n"
    message += f"{role_emoji}\n"
    message += f"ID: {active_project['project_id']}\n"
    message += f"Создан: {active_project['created_date']}\n"
    message += format_project_totals(stats) + "\n"
    message += f"Участников: {len(members)}\n\n"

    # Add quick actions button
    keyboard = [[InlineKeyboardButton("⚙️ Управление проектом", callback_data=f"proj_settings_{active_project['project_id']}")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(message, reply_markup=reply_markup)

def register_project_handlers(application):
    """
    Регистрирует обработчики команд для работы с проектами
    """

    # Команды (с /)
    application.add_handler(CommandHandler("project_list", project_list_command))
    application.add_handler(CommandHandler("project_select", project_select_command))
    application.add_handler(CommandHandler("project_main", project_main_command))
    application.add_handler(CommandHandler("project_info", project_info_command))  # Новая команда для info

    # Conversation для удаления (с entry для команды и кнопки)
    delete_conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("project_delete", project_delete_start),
            MessageHandler(filters.Regex(project_menu_button_regex("delete")), button_project_delete_start)
        ],
        states={
            # Пользователь выбирает проект из инлайн-меню
            CHOOSING_PROJECT_TO_DELETE: [
                CallbackQueryHandler(project_delete_choose_callback, pattern=r'^del_proj_')
            ],
            # Пользователь подтверждает удаление выбранного проекта
            CONFIRMING_DELETE: [
                CallbackQueryHandler(project_delete_confirm, pattern=r'^(del_confirm_\d+|del_proj_cancel)$')
            ],
        },
        fallbacks=[CommandHandler("cancel", project_cancel)],
        name="delete_project_conversation",
        persistent=False,
    )
    application.add_handler(delete_conv_handler)

    # Conversation для создания (кнопка): ввод имени → выбор шаблона → создание
    create_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("project_create", project_create_command), MessageHandler(filters.Regex(project_menu_button_regex("create")), button_project_create_start)],
        states={
            ENTERING_PROJECT_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, button_project_create_name)],
            CHOOSING_TEMPLATE: [CallbackQueryHandler(button_project_create_template, pattern=r'^tpl_')],
            CHOOSING_REPORT_CURRENCY: [CallbackQueryHandler(project_report_currency, pattern=r'^proj_report_')],
            CHOOSING_INPUT_CURRENCY: [CallbackQueryHandler(project_input_currency, pattern=r'^proj_input_')],
            ENTERING_FALLBACK_RATE: [CommandHandler('skip', project_fallback_rate), MessageHandler(filters.TEXT & ~filters.COMMAND, project_fallback_rate)],
        },
        fallbacks=[CommandHandler("cancel", project_cancel)],
        name="create_project_conversation",
        persistent=False
    )
    application.add_handler(create_conv_handler)

    # Обработчик выбора проекта через кнопку (показывает меню)
    application.add_handler(MessageHandler(filters.Regex(project_menu_button_regex("select")), button_project_select_start))

    # Callback handler для выбора проекта из списка
    application.add_handler(CallbackQueryHandler(handle_project_selection_callback, pattern=r'^select_proj_(none|\d+)$'))

    # Простые кнопки (без ввода)
    application.add_handler(MessageHandler(filters.Regex(project_menu_button_regex("list")), project_list_command))
    application.add_handler(MessageHandler(filters.Regex(project_menu_button_regex("all_expenses")), project_main_command))
    application.add_handler(MessageHandler(filters.Regex(project_menu_button_regex("info")), project_info_command))

    # Settings button - imported from project_management
    from handlers.project_management import project_settings_menu
    application.add_handler(MessageHandler(filters.Regex(project_menu_button_regex("settings")), project_settings_menu))

