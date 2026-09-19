"""Currency selection and settings for personal and shared accounting."""

import re

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ConversationHandler,
    MessageHandler,
    filters,
)

import config
from utils import currencies, helpers, projects

MENU, SELECTING, RATE = range(3)


def currency_keyboard(prefix: str, codes=None, default=None, other=False):
    """Build a deduplicated currency picker with unambiguous names."""
    codes = list(dict.fromkeys(codes or currencies.CURRENCIES))
    rows = []
    for code in codes:
        if code not in currencies.CURRENCIES:
            continue
        name = currencies.CURRENCIES[code]["name"]
        label = f"{name} · {code}" + (" ✓" if code == default else "")
        rows.append([InlineKeyboardButton(label, callback_data=f"{prefix}{code}")])
    if other:
        rows.append([InlineKeyboardButton(config.CURRENCY_BUTTONS["other"], callback_data=f"{prefix}other")])
    return InlineKeyboardMarkup(rows)


def remember_currency(context, project_id, code):
    """Recent currencies are scoped to this user and accounting context."""
    recent = context.user_data.setdefault("recent_currencies", {})
    key = str(project_id)
    recent[key] = list(dict.fromkeys([code, *recent.get(key, [])]))[:3]


async def input_keyboard(user_id, project_id, context, prefix):
    default = await currencies.get_input_currency(user_id, project_id)
    report = await currencies.get_reporting_currency(user_id, project_id)
    recent = context.user_data.get("recent_currencies", {}).get(str(project_id), [])
    return currency_keyboard(prefix, [default, report, *recent], default, other=True)


def format_snapshot(money):
    """Show the original currency and the frozen conversion source."""
    if not money:
        return "сумма не указана"
    result = currencies.format_money(money["amount"], money["currency"])
    if money["currency"] != money["reporting_currency"]:
        result += " ≈ " + currencies.format_money(money["reporting_amount"], money["reporting_currency"])
    if money.get("fx_source") == "manual":
        result += "\nИспользован резервный курс."
    return result


async def _reply(update, text, **kwargs):
    if update.callback_query:
        await update.callback_query.edit_message_text(text, **kwargs)
    else:
        await update.message.reply_text(text, **kwargs)


async def _show_settings(update, context):
    uid = update.effective_user.id
    pid = context.user_data["currency_project_id"]
    report = await currencies.get_reporting_currency(uid, pid)
    default = await currencies.get_input_currency(uid, pid)
    project = await projects.get_project_by_id(uid, pid) if pid is not None else None
    if pid is not None and not project:
        raise currencies.CurrencyError("Проект недоступен.")
    owner = pid is None or project.get("is_owner") or project.get("role") == "owner"
    context.user_data["currency_can_manage"] = bool(owner)
    rows = [[InlineKeyboardButton(config.CURRENCY_BUTTONS["input"], callback_data="cur_input")]]
    if owner:
        rows.extend([[InlineKeyboardButton(config.CURRENCY_BUTTONS[k], callback_data=f"cur_{k}")] for k in ("report", "fallback")])
    rows.append([InlineKeyboardButton(config.CURRENCY_BUTTONS["cancel"], callback_data="cur_cancel")])
    scope = project["project_name"] if project else "Личный учёт"
    await _reply(update, f"💱 {scope}\nВалюта отчётности: {report}\nВаша валюта ввода: {default}\n\n"
                 "Разовый выбор валюты расхода не меняет валюту ввода.\n"
                 "Валюта отчётности фиксируется после появления денежных данных.",
                 reply_markup=InlineKeyboardMarkup(rows))
    return MENU


async def currency_command(update: Update, context):
    if update.callback_query:
        await update.callback_query.answer()
        pid = int(update.callback_query.data.rsplit("_", 1)[1])
    else:
        pid = await helpers.get_active_project_id(update.effective_user.id, context)
    context.user_data["currency_project_id"] = pid
    try:
        return await _show_settings(update, context)
    except (currencies.CurrencyError, PermissionError) as exc:
        await _reply(update, f"❌ {exc}")
        return ConversationHandler.END


async def currency_action(update: Update, context):
    query = update.callback_query
    await query.answer()
    action = query.data.removeprefix("cur_")
    if action == "cancel":
        return await cancel(update, context)
    if "currency_project_id" not in context.user_data or action not in ("input", "report", "fallback"):
        await _reply(update, "❌ Откройте /currency заново.")
        return ConversationHandler.END
    if action != "input" and not context.user_data.get("currency_can_manage"):
        await _reply(update, "❌ Настройка доступна владельцу проекта.")
        return ConversationHandler.END
    context.user_data["currency_action"] = action
    prompt = "Выберите валюту, для которой хотите задать резервный курс:" if action == "fallback" else "Выберите валюту:"
    await _reply(update, prompt, reply_markup=currency_keyboard("cur_code_"))
    return SELECTING


async def currency_selected(update: Update, context):
    await update.callback_query.answer()
    if "currency_project_id" not in context.user_data:
        await _reply(update, "❌ Откройте /currency заново.")
        return ConversationHandler.END
    uid = update.effective_user.id
    pid = context.user_data["currency_project_id"]
    try:
        code = currencies.normalize_currency(update.callback_query.data.removeprefix("cur_code_"))
        action = context.user_data.get("currency_action")
        if action == "input":
            await currencies.set_input_currency(uid, pid, code)
        elif action == "report":
            await currencies.set_reporting_currency(uid, pid, code)
        elif action == "fallback":
            report = await currencies.get_reporting_currency(uid, pid)
            if code == report:
                raise currencies.CurrencyError("Для одинаковых валют курс всегда равен 1.")
            context.user_data["currency_source"] = code
            await _reply(update, f"Сколько {report} стоит 1 {code}?\nВведите положительное число.\n"
                         "Этот курс используется, если автоматический недоступен. Старые записи не изменятся.")
            return RATE
        else:
            raise currencies.CurrencyError("Откройте /currency заново.")
        return await _show_settings(update, context)
    except (currencies.CurrencyError, PermissionError) as exc:
        await _reply(update, f"❌ {exc}\nОткройте /currency для настройки.")
        return ConversationHandler.END


async def currency_rate(update: Update, context):
    if 'currency_project_id' not in context.user_data or 'currency_source' not in context.user_data:
        await _reply(update, 'Откройте /currency заново.')
        return ConversationHandler.END
    try:
        await currencies.set_fallback_rate(update.effective_user.id, context.user_data["currency_project_id"],
                                           context.user_data["currency_source"], update.message.text)
        await update.message.reply_text("✅ Резервный курс сохранён. Он применяется к новым операциям.")
        return await _show_settings(update, context)
    except (currencies.CurrencyError, PermissionError) as exc:
        await update.message.reply_text(f"❌ {exc}\nВведите курс ещё раз или /cancel.")
        return RATE


async def cancel(update: Update, context):
    for key in ("currency_project_id", "currency_action", "currency_source", "currency_can_manage"):
        context.user_data.pop(key, None)
    await _reply(update, "Настройка валют завершена.")
    return ConversationHandler.END


def register_currency_handlers(application):
    application.add_handler(ConversationHandler(
        entry_points=[CommandHandler("currency", currency_command),
                      MessageHandler(filters.Regex("^" + re.escape(config.SETTINGS_MENU_BUTTONS["currency"]) + "$"), currency_command),
                      CallbackQueryHandler(currency_command, pattern=r"^currency_project_\d+$")],
        states={MENU: [CallbackQueryHandler(currency_action, pattern=r"^cur_(input|report|fallback|cancel)$")],
                SELECTING: [CallbackQueryHandler(currency_selected, pattern=r"^cur_code_")],
                RATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, currency_rate)]},
        fallbacks=[CommandHandler("cancel", cancel)], name="currency_settings", persistent=False,
        allow_reentry=True,
    ))
