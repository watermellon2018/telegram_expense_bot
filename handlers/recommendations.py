"""
Telegram handler for recommendation pipeline integration.
"""

import datetime
import time
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

from metrics import (
    classify_error_type,
    track_command,
    track_handler_error,
    track_handler_start,
    track_handler_success,
)
from recommendation import (
    BaselineOutlierHandler,
    DefaultRecommendationFormatter,
    RecommendationFeedbackActionType,
    RecommendationFeedbackService,
    DefaultRuleEngine,
    PreparedAnalyticsService,
    RecommendationPipeline,
    RecommendationRequest,
    ScoreRankingService,
)
from recommendation.repositories import (
    PostgresFeedbackRepository,
    PostgresHistoryRepository,
    PostgresSettingsRepository,
)
from recommendation.rules import build_mvp_rules
from utils import excel, helpers, incomes
from utils.logger import get_logger, log_error, log_event

logger = get_logger("handlers.recommendations")

_FEEDBACK_USAGE = (
    "Использование:\n"
    "/rec_like <recommendation_id>\n"
    "/rec_dislike <recommendation_id>\n"
    "/rec_dismiss <recommendation_id>"
)


def _build_pipeline() -> RecommendationPipeline:
    return RecommendationPipeline(
        analytics_service=PreparedAnalyticsService(),
        outlier_handler=BaselineOutlierHandler(),
        rule_engine=DefaultRuleEngine(build_mvp_rules()),
        ranking_service=ScoreRankingService(),
        formatter=DefaultRecommendationFormatter(),
        settings_repository=PostgresSettingsRepository(),
        history_repository=PostgresHistoryRepository(),
        feedback_repository=PostgresFeedbackRepository(),
    )


async def recommendations_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    track_command("recommendations")
    track_handler_start("recommendations_command")
    error_type = None
    started_at = time.time()

    user = update.effective_user
    if user is None or update.message is None:
        track_handler_success("recommendations_command")
        return

    user_id = str(user.id)
    project_id = context.user_data.get("active_project_id")
    try:
        pipeline = _build_pipeline()
        request = await _build_request(user_id=user_id, project_id=project_id)
        recommendations = await pipeline.generate(request)

        if not recommendations:
            await update.message.reply_text(
                "Пока нет устойчивых сигналов для рекомендаций. "
                "Нужно чуть больше данных за период.",
                reply_markup=helpers.get_main_menu_keyboard(),
            )
            log_event(
                logger,
                "recommendations_empty",
                user_id=user_id,
                project_id=project_id,
                duration=time.time() - started_at,
            )
            return

        period_label = request.requested_at.strftime("%m.%Y")
        lines: List[str] = [f"💡 Рекомендации за {period_label}:\n"]
        for index, item in enumerate(recommendations, start=1):
            lines.append(f"{index}. {item.title}")
            lines.append(item.message)
            lines.append(f"ID: {item.recommendation_id}")
            lines.append("")

        await _store_shown_feedback_events(
            user_id=user_id,
            project_id=project_id,
            recommendation_ids=[item.recommendation_id for item in recommendations],
        )

        await update.message.reply_text(
            "\n".join(lines).strip(),
            reply_markup=helpers.get_main_menu_keyboard(),
        )
        log_event(
            logger,
            "recommendations_sent",
            user_id=user_id,
            project_id=project_id,
            count=len(recommendations),
            duration=time.time() - started_at,
        )
    except Exception as exc:
        error_type = classify_error_type(exc)
        log_error(
            logger,
            exc,
            "recommendations_command_error",
            user_id=user_id,
            project_id=project_id,
            duration=time.time() - started_at,
        )
        await update.message.reply_text(
            "❌ Не удалось сформировать рекомендации. Попробуйте позже.",
            reply_markup=helpers.get_main_menu_keyboard(),
        )
    finally:
        if error_type:
            track_handler_error("recommendations_command", error_type)
        else:
            track_handler_success("recommendations_command")


async def recommendation_like_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _save_feedback_action(
        update=update,
        context=context,
        action=RecommendationFeedbackActionType.LIKED,
    )


async def recommendation_dislike_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _save_feedback_action(
        update=update,
        context=context,
        action=RecommendationFeedbackActionType.DISLIKED,
    )


async def recommendation_dismiss_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _save_feedback_action(
        update=update,
        context=context,
        action=RecommendationFeedbackActionType.DISMISSED,
    )


async def _build_request(
    user_id: str,
    project_id: Optional[int],
) -> RecommendationRequest:
    now = datetime.datetime.now()
    current_month = now.month
    current_year = now.year

    prev_month, prev_year = _shift_month(current_month, current_year, -1)
    baseline_periods = [_shift_month(current_month, current_year, -step) for step in (1, 2, 3)]

    current_expenses = await excel.get_month_expenses(user_id, current_month, current_year, project_id)
    prev_expenses = await excel.get_month_expenses(user_id, prev_month, prev_year, project_id)
    current_incomes = await incomes.get_month_incomes(user_id, current_month, current_year, project_id)
    prev_incomes = await incomes.get_month_incomes(user_id, prev_month, prev_year, project_id)

    expenses_df = await excel.get_all_expenses(user_id, current_year, project_id)
    incomes_df = await incomes.get_all_incomes(user_id, current_year, project_id)

    expense_records = _to_records(expenses_df)
    income_records = _to_records(incomes_df)
    recurring_pairs = _detect_recurring_pairs(expense_records)

    current_expense_events = _build_expense_events_for_month(
        records=expense_records,
        month=current_month,
        recurring_pairs=recurring_pairs,
    )
    current_income_events = _build_income_events_for_month(income_records, current_month)
    current_events = current_expense_events + current_income_events

    prev_month_expense_events = _build_expense_events_for_month(
        records=expense_records,
        month=prev_month,
        recurring_pairs=recurring_pairs,
    )

    prev_month_expense_total = _safe_total(prev_expenses, "total")
    prev_month_income_total = _safe_total(prev_incomes, "total")
    prev_month_net_balance = prev_month_income_total - prev_month_expense_total

    baseline_totals = []
    baseline_category_shares: Dict[str, List[float]] = {}
    for month, year in baseline_periods:
        month_stats = await excel.get_month_expenses(user_id, month, year, project_id)
        month_total = _safe_total(month_stats, "total")
        if month_total <= 0:
            continue
        baseline_totals.append(month_total)
        month_shares = _category_share_map(month_stats)
        for category_key, share in month_shares.items():
            baseline_category_shares.setdefault(category_key, []).append(share)

    if baseline_totals:
        total_expense_3m_baseline = sum(baseline_totals) / len(baseline_totals)
    else:
        total_expense_3m_baseline = prev_month_expense_total

    category_share_3m_baseline = {
        key: (sum(values) / len(values))
        for key, values in baseline_category_shares.items()
        if values
    }

    same_day_prev_month_expense = _sum_same_day_prev_month(prev_month_expense_events, now.day)
    prev_month_recurring_share = _calculate_recurring_share(prev_month_expense_events)

    period_start = datetime.date(current_year, current_month, 1)
    next_month, next_month_year = _shift_month(current_month, current_year, 1)
    period_end = datetime.date(next_month_year, next_month, 1) - datetime.timedelta(days=1)

    metrics = {
        "total_expense_prev_month": prev_month_expense_total,
        "total_expense_3m_baseline": total_expense_3m_baseline,
        "same_day_prev_month_expense": same_day_prev_month_expense,
        "prev_month_net_balance": prev_month_net_balance,
        "prev_month_recurring_share": prev_month_recurring_share,
    }
    dimensions = {
        "category_share_prev_month": _category_share_map(prev_expenses),
        "category_share_3m_baseline": category_share_3m_baseline,
    }

    return RecommendationRequest(
        user_id=user_id,
        project_id=project_id,
        requested_at=now,
        period_start=period_start,
        period_end=period_end,
        metrics=metrics,
        dimensions=dimensions,
        events=current_events,
        metadata={
            "period_key": now.strftime("%Y-%m"),
            "small_expense_threshold": 200.0,
        },
    )


def _shift_month(month: int, year: int, delta: int) -> Tuple[int, int]:
    shifted = (year * 12 + (month - 1)) + delta
    return (shifted % 12) + 1, shifted // 12


def _to_records(dataframe) -> Sequence[Mapping[str, object]]:
    if dataframe is None:
        return []
    if getattr(dataframe, "empty", True):
        return []
    return list(dataframe.to_dict(orient="records"))


def _detect_recurring_pairs(records: Sequence[Mapping[str, object]]) -> Sequence[Tuple[str, float]]:
    counts: Dict[Tuple[str, float], int] = {}
    for item in records:
        amount = _to_float(item.get("amount"))
        if amount <= 0:
            continue
        category = str(item.get("category") or "uncategorized")
        key = (category, round(amount, 2))
        counts[key] = counts.get(key, 0) + 1
    return [key for key, count in counts.items() if count >= 3]


def _build_expense_events_for_month(
    records: Sequence[Mapping[str, object]],
    month: int,
    recurring_pairs: Sequence[Tuple[str, float]],
) -> List[Mapping[str, object]]:
    recurring_pairs_set = set(recurring_pairs)
    events: List[Mapping[str, object]] = []
    for item in records:
        item_month = _to_int(item.get("month"))
        if item_month != month:
            continue
        amount = _to_float(item.get("amount"))
        if amount <= 0:
            continue
        category = str(item.get("category") or "uncategorized")
        recurring_key = (category, round(amount, 2))
        event_date = _to_iso_date(item.get("date"))
        if event_date is None:
            continue
        events.append(
            {
                "date": event_date,
                "amount": amount,
                "type": "expense",
                "category": category,
                "is_recurring": recurring_key in recurring_pairs_set,
            }
        )
    return events


def _build_income_events_for_month(
    records: Sequence[Mapping[str, object]],
    month: int,
) -> List[Mapping[str, object]]:
    events: List[Mapping[str, object]] = []
    for item in records:
        item_month = _to_int(item.get("month"))
        if item_month != month:
            continue
        amount = _to_float(item.get("amount"))
        if amount <= 0:
            continue
        event_date = _to_iso_date(item.get("date"))
        if event_date is None:
            continue
        events.append(
            {
                "date": event_date,
                "amount": amount,
                "type": "income",
                "category": str(item.get("category") or "income"),
            }
        )
    return events


def _sum_same_day_prev_month(events: Sequence[Mapping[str, object]], day_limit: int) -> float:
    total = 0.0
    for item in events:
        event_day = _day_from_iso(item.get("date"))
        if event_day is None or event_day > day_limit:
            continue
        total += _to_float(item.get("amount"))
    return total


def _calculate_recurring_share(events: Sequence[Mapping[str, object]]) -> float:
    total = 0.0
    recurring = 0.0
    for item in events:
        amount = _to_float(item.get("amount"))
        total += amount
        if bool(item.get("is_recurring", False)):
            recurring += amount
    if total <= 0:
        return 0.0
    return recurring / total


def _category_share_map(month_expenses: Optional[Mapping[str, object]]) -> Mapping[str, float]:
    if not month_expenses:
        return {}
    total = _safe_total(month_expenses, "total")
    by_category = month_expenses.get("by_category") or {}
    if total <= 0 or not isinstance(by_category, Mapping):
        return {}
    return {
        str(category): (_to_float(value) / total)
        for category, value in by_category.items()
        if _to_float(value) > 0
    }


def _safe_total(data: Optional[Mapping[str, object]], key: str) -> float:
    if not data:
        return 0.0
    return _to_float(data.get(key))


def _to_float(value: object) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _to_int(value: object) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _to_iso_date(value: object) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, datetime.datetime):
        return value.date().isoformat()
    if isinstance(value, datetime.date):
        return value.isoformat()
    try:
        return datetime.datetime.fromisoformat(str(value)).date().isoformat()
    except ValueError:
        return None


def _day_from_iso(value: object) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, datetime.date):
        return value.day
    try:
        return datetime.date.fromisoformat(str(value)).day
    except ValueError:
        return None


async def _store_shown_feedback_events(
    user_id: str,
    project_id: Optional[int],
    recommendation_ids: Sequence[str],
) -> None:
    if not recommendation_ids:
        return

    service = RecommendationFeedbackService(PostgresFeedbackRepository())
    for recommendation_id in recommendation_ids:
        try:
            await service.add_feedback_event(
                recommendation_id=recommendation_id,
                user_id=user_id,
                action_type=RecommendationFeedbackActionType.SHOWN,
                metadata_json={
                    "source": "recommendations_command",
                    "project_id": project_id,
                },
            )
        except Exception as exc:
            log_error(
                logger,
                exc,
                "recommendations_shown_feedback_error",
                user_id=user_id,
                recommendation_id=recommendation_id,
                project_id=project_id,
            )


async def _save_feedback_action(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    action: RecommendationFeedbackActionType,
) -> None:
    if update.message is None or update.effective_user is None:
        return

    if not context.args:
        await update.message.reply_text(_FEEDBACK_USAGE, reply_markup=helpers.get_main_menu_keyboard())
        return

    recommendation_id = str(context.args[0]).strip()
    if not recommendation_id:
        await update.message.reply_text(_FEEDBACK_USAGE, reply_markup=helpers.get_main_menu_keyboard())
        return

    user_id = str(update.effective_user.id)
    project_id = context.user_data.get("active_project_id")
    service = RecommendationFeedbackService(PostgresFeedbackRepository())
    try:
        await service.add_feedback_event(
            recommendation_id=recommendation_id,
            user_id=user_id,
            action_type=action,
            metadata_json={
                "source": "feedback_command",
                "project_id": project_id,
            },
        )
        await update.message.reply_text(
            "✅ Feedback сохранен.",
            reply_markup=helpers.get_main_menu_keyboard(),
        )
        log_event(
            logger,
            "recommendation_feedback_saved",
            user_id=user_id,
            recommendation_id=recommendation_id,
            action=action.value,
            project_id=project_id,
        )
    except Exception as exc:
        log_error(
            logger,
            exc,
            "recommendation_feedback_save_error",
            user_id=user_id,
            recommendation_id=recommendation_id,
            action=action.value,
            project_id=project_id,
        )
        await update.message.reply_text(
            "❌ Не удалось сохранить feedback.",
            reply_markup=helpers.get_main_menu_keyboard(),
        )


def register_recommendation_handlers(application) -> None:
    application.add_handler(CommandHandler("recommendations", recommendations_command))
    application.add_handler(CommandHandler("rec_like", recommendation_like_command))
    application.add_handler(CommandHandler("rec_dislike", recommendation_dislike_command))
    application.add_handler(CommandHandler("rec_dismiss", recommendation_dismiss_command))
