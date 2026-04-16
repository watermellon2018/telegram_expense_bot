"""
Обнаружение повторяющихся паттернов в истории расходов.

Используется простая эвристика без ML:
- Группировка по (category_id, нормализованный comment)
- Фильтрация по количеству, дисперсии суммы и дисперсии интервалов
- Классификация частоты по среднему интервалу

После обнаружения паттерна бот предлагает пользователю создать постоянный расход.
"""

import re
import datetime
import hashlib
from typing import Optional

from utils import db
from utils.logger import get_logger, log_event

logger = get_logger("utils.pattern_detector")

# ---------------------------------------------------------------------------
# Константы
# ---------------------------------------------------------------------------

# Минимум транзакций для признания паттерна
MIN_TRANSACTIONS = 3

# Максимальный коэффициент вариации суммы (стандартное отклонение / среднее)
AMOUNT_CV_THRESHOLD = 0.15  # ±15%

# Максимальный коэффициент вариации интервала
INTERVAL_CV_THRESHOLD = 0.20  # ±20%

# Глубина анализа истории
LOOKBACK_DAYS = 90

# Cooldown между предложениями (не предлагать снова в течение N дней)
SUGGEST_COOLDOWN_DAYS = 7


# ---------------------------------------------------------------------------
# Нормализация
# ---------------------------------------------------------------------------

def normalize_comment(comment: str) -> str:
    """
    Нормализует комментарий для группировки похожих расходов.
    Приводит к нижнему регистру и удаляет лишние пробелы.
    """
    return comment.lower().strip()


def comment_hash(comment: str) -> str:
    """
    Возвращает короткий хэш нормализованного комментария (8 символов hex).
    Используется как ключ в bot_data для cooldown-записей.
    """
    normalized = normalize_comment(comment)
    return hashlib.md5(normalized.encode('utf-8')).hexdigest()[:8]


# ---------------------------------------------------------------------------
# Основная функция обнаружения паттерна
# ---------------------------------------------------------------------------

async def detect_pattern_for_user(
    user_id: str,
    project_id: Optional[int],
    category_id: int,
    comment: str,
) -> Optional[dict]:
    """
    Ищет повторяющийся паттерн расходов для комбинации (category_id, comment).

    Возвращает dict с описанием паттерна или None если паттерн не найден.

    Алгоритм:
    1. Выбрать расходы за последние LOOKBACK_DAYS дней
       с matching category_id и нормализованным comment
    2. Если транзакций < MIN_TRANSACTIONS → None
    3. Коэффициент вариации суммы > AMOUNT_CV_THRESHOLD → None
    4. Вычислить интервалы между датами (дней)
    5. Коэффициент вариации интервалов > INTERVAL_CV_THRESHOLD → None
    6. Классифицировать частоту по среднему интервалу:
       ≤ 2 дня  → daily
       ≤ 9 дней → weekly
       ≤ 35 дней → monthly
       иначе    → every_n_days с interval_value = round(avg_interval)
    7. Вернуть описание паттерна

    Возвращаемый dict:
        {
            'amount':         float,        # средняя сумма
            'category_id':    int,
            'comment':        str,          # оригинальный комментарий
            'frequency_type': str,
            'interval_value': int | None,   # None для daily/weekly/monthly
        }
    """
    if not comment or not comment.strip():
        return None

    norm_comment = normalize_comment(comment)
    cutoff = datetime.date.today() - datetime.timedelta(days=LOOKBACK_DAYS)

    try:
        if project_id is None:
            rows = await db.fetch(
                """
                SELECT e.amount, e.date
                FROM expenses e
                WHERE e.user_id = $1
                  AND e.category_id = $2
                  AND e.project_id IS NULL
                  AND e.date >= $3
                  AND e.source_type IS DISTINCT FROM 'recurring'
                  AND LOWER(TRIM(COALESCE(e.description, ''))) = $4
                ORDER BY e.date ASC
                """,
                user_id, category_id, cutoff, norm_comment,
            )
        else:
            rows = await db.fetch(
                """
                SELECT e.amount, e.date
                FROM expenses e
                WHERE e.project_id = $1
                  AND e.category_id = $2
                  AND e.date >= $3
                  AND e.source_type IS DISTINCT FROM 'recurring'
                  AND LOWER(TRIM(COALESCE(e.description, ''))) = $4
                ORDER BY e.date ASC
                """,
                project_id, category_id, cutoff, norm_comment,
            )
    except Exception:
        return None

    if len(rows) < MIN_TRANSACTIONS:
        return None

    amounts = [float(r['amount']) for r in rows]
    dates = [r['date'] for r in rows]

    # --- Проверка дисперсии суммы ---
    avg_amount = sum(amounts) / len(amounts)
    if avg_amount <= 0:
        return None
    std_amount = _std(amounts, avg_amount)
    cv_amount = std_amount / avg_amount
    if cv_amount > AMOUNT_CV_THRESHOLD:
        return None

    # --- Проверка дисперсии интервалов ---
    # Для N дат получаем N-1 интервал
    intervals = [(dates[i + 1] - dates[i]).days for i in range(len(dates) - 1)]
    if not intervals:
        return None

    avg_interval = sum(intervals) / len(intervals)
    if avg_interval <= 0:
        return None

    std_interval = _std(intervals, avg_interval)
    cv_interval = std_interval / avg_interval
    if cv_interval > INTERVAL_CV_THRESHOLD:
        return None

    # --- Классификация частоты ---
    frequency_type, interval_value = _classify_frequency(avg_interval)

    log_event(logger, "pattern_detected",
              user_id=user_id, category_id=category_id,
              comment=comment, frequency_type=frequency_type,
              avg_interval=round(avg_interval, 1), count=len(rows))

    return {
        'amount': round(avg_amount, 2),
        'category_id': category_id,
        'comment': comment,
        'frequency_type': frequency_type,
        'interval_value': interval_value,
    }


def _std(values: list, mean: float) -> float:
    """Стандартное отклонение для списка значений."""
    if len(values) < 2:
        return 0.0
    variance = sum((v - mean) ** 2 for v in values) / len(values)
    return variance ** 0.5


def _classify_frequency(avg_interval: float) -> tuple:
    """
    Классифицирует частоту по среднему интервалу в днях.

    Возвращает (frequency_type, interval_value).

    Пороги:
        ≤ 2 дня   → ('daily', None)
        ≤ 9 дней  → ('weekly', None)
        ≤ 35 дней → ('monthly', None)
        > 35 дней → ('every_n_days', round(avg_interval))
    """
    if avg_interval <= 2:
        return 'daily', None
    if avg_interval <= 9:
        return 'weekly', None
    if avg_interval <= 35:
        return 'monthly', None
    return 'every_n_days', round(avg_interval)


# ---------------------------------------------------------------------------
# Управление cooldown в bot_data
# ---------------------------------------------------------------------------

def is_on_cooldown(bot_data: dict, user_id: str, com: str) -> bool:
    """
    Проверяет, предлагали ли мы этот паттерн пользователю недавно.

    Cooldown хранится в bot_data['rec_cooldowns'][user_id][comment_hash].
    Возвращает True если cooldown ещё не истёк.
    """
    cooldowns = bot_data.get('rec_cooldowns', {})
    user_cooldowns = cooldowns.get(user_id, {})
    key = comment_hash(com)
    last_suggest = user_cooldowns.get(key)
    if last_suggest is None:
        return False
    elapsed = datetime.datetime.utcnow() - last_suggest
    return elapsed.days < SUGGEST_COOLDOWN_DAYS


def set_cooldown(bot_data: dict, user_id: str, com: str) -> None:
    """
    Записывает момент предложения в bot_data для cooldown-логики.
    Вызывается после отклонения или создания правила по предложению.
    """
    if 'rec_cooldowns' not in bot_data:
        bot_data['rec_cooldowns'] = {}
    if user_id not in bot_data['rec_cooldowns']:
        bot_data['rec_cooldowns'][user_id] = {}
    bot_data['rec_cooldowns'][user_id][comment_hash(com)] = datetime.datetime.utcnow()


def save_pattern_to_cache(bot_data: dict, user_id: str, pattern: dict) -> None:
    """
    Сохраняет найденный паттерн в bot_data для использования при нажатии «Да».
    Ключ: f"{user_id}_{comment_hash(pattern['comment'])}".
    """
    if 'rec_patterns' not in bot_data:
        bot_data['rec_patterns'] = {}
    key = f"{user_id}_{comment_hash(pattern['comment'])}"
    bot_data['rec_patterns'][key] = pattern


def get_pattern_from_cache(bot_data: dict, user_id: str, com: str) -> Optional[dict]:
    """Извлекает кэшированный паттерн. Возвращает None если не найден."""
    patterns = bot_data.get('rec_patterns', {})
    key = f"{user_id}_{comment_hash(com)}"
    return patterns.get(key)


# ---------------------------------------------------------------------------
# Парсинг пользовательского ввода частоты
# ---------------------------------------------------------------------------

def parse_custom_frequency(text: str) -> Optional[dict]:
    """
    Парсит текстовый ввод пользователя и возвращает параметры частоты.

    Поддерживаемые форматы (регистронезависимо):
        "каждый день"              → {'frequency_type': 'daily'}
        "каждые 3 дня"             → {'frequency_type': 'every_n_days', 'interval_value': 3}
        "каждую неделю"            → {'frequency_type': 'weekly'}
        "каждые 2 недели"          → {'frequency_type': 'every_n_weeks', 'interval_value': 2}
        "каждый месяц"             → {'frequency_type': 'monthly'}
        "каждые 3 месяца"          → {'frequency_type': 'every_n_months', 'interval_value': 3}
        "1 числа" / "15 числа"     → {'frequency_type': 'monthly', 'day_of_month': 15}
        "последний день месяца"    → {'frequency_type': 'monthly', 'is_last_day_of_month': True}

    Возвращает None если формат не распознан.
    """
    t = text.lower().strip()
    # Удаляем лишние пробелы
    t = re.sub(r'\s+', ' ', t)

    # --- каждые N дней ---
    m = re.search(r'каждые?\s+(\d+)\s+дн', t)
    if m:
        n = int(m.group(1))
        if n >= 1:
            return {'frequency_type': 'every_n_days', 'interval_value': n}

    # --- каждые N недель ---
    m = re.search(r'каждые?\s+(\d+)\s+недел', t)
    if m:
        n = int(m.group(1))
        if n >= 1:
            return {'frequency_type': 'every_n_weeks', 'interval_value': n}

    # --- каждые N месяцев ---
    m = re.search(r'каждые?\s+(\d+)\s+месяц', t)
    if m:
        n = int(m.group(1))
        if n >= 1:
            return {'frequency_type': 'every_n_months', 'interval_value': n}

    # --- каждый день ---
    if re.search(r'каждый?\s+день|ежедневн', t):
        return {'frequency_type': 'daily'}

    # --- каждую неделю ---
    if re.search(r'каждую?\s+недел|еженедел', t):
        return {'frequency_type': 'weekly'}

    # --- каждый месяц ---
    if re.search(r'каждый?\s+месяц|ежемесяч', t):
        return {'frequency_type': 'monthly'}

    # --- N-го числа / N числа ---
    m = re.search(r'(\d+)\s*[-го]*\s*числ', t)
    if m:
        day = int(m.group(1))
        if 1 <= day <= 31:
            return {'frequency_type': 'monthly', 'day_of_month': day}

    # --- последний день месяца ---
    if re.search(r'последн', t) and re.search(r'(день|число|дн)', t):
        return {'frequency_type': 'monthly', 'is_last_day_of_month': True}

    return None
