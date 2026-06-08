# 3. Telegram интерфейс и маршрутизация

## 3.1. Главные принципы

- Регистрация обработчиков централизована в `handlers/registry.py`.
- Порядок регистрации критичен.
- UI построен на комбинации:
  - slash-команд (`CommandHandler`);
  - кнопок reply keyboard (`MessageHandler + Regex`);
  - inline callback (`CallbackQueryHandler`);
  - state-machine сценариев (`ConversationHandler`).

## 3.2. Порядок регистрации (важно)

Последним регистрируется `handlers/expense.py`, потому что там есть общий текстовый handler:

- `MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler)`.

Если поднять его выше, он начнет перехватывать сообщения, которые должны обрабатываться другими модулями.

## 3.3. Главное меню и подменю

Меню собирается в `utils/menu.py` из кнопок `config.py`.

Главное меню:

- `➕ Добавить`
- `📅 Месяц`
- `📆 День`
- `💵 Доходы`
- `💰 Бюджет`
- `⚙️ Настройки`
- `📁 Проекты`
- `🔍 Анализ`
- `💳 Кэшбэк`
- `❓ Помощь`

Подменю:

- Анализ: статистика, отчет, экспорт.
- Доходы: добавить, категории, recurring incomes.
- Настройки: категории, recurring expenses.
- Кэшбэк: карты, правила, категории, экономия.
- Проекты: создать/список/выбрать/инфо/управление/удаление.

## 3.4. Ключевые команды

### Базовые

- `/start`
- `/help`

### Расходы и аналитика

- `/add`
- `/month`
- `/day`
- `/stats`
- `/category`
- `/export`
- `/report`

### Проекты и участники

- `/project_create`
- `/project_list`
- `/project_select`
- `/project_main`
- `/project_info`
- `/project_delete`
- `/project_settings`
- `/invite`
- `/members`

### Доходы

- `/income_add` (и кнопочный flow)

### Кэшбэк

- `/cashback`
- `/cashback_cards`
- `/cashback_rules`
- `/cashback_stats`
- `/cashback_card_add`
- `/cashback_card_activate`
- `/cashback_card_deactivate`
- `/cashback_card_delete`
- `/cashback_category_add`
- `/cashback_rule_add`
- `/cashback_rule_edit`
- `/cashback_rule_remove`

### Рекомендации

- `/recommendations`
- `/rec_like`
- `/rec_dislike`
- `/rec_dismiss`

## 3.5. Conversation-сценарии (основные)

- `handlers/expense.py`
  - сумма -> категория -> описание.

- `handlers/budget.py`
  - установка бюджета: сумма -> уведомления -> порог.
  - редактирование порога уведомлений.

- `handlers/category.py`
  - создание/деактивация категорий расходов.

- `handlers/income.py` и `handlers/income_category.py`
  - создание дохода и управление income category.

- `handlers/recurring.py`
  - recurring expense: сумма -> категория -> комментарий -> частота.
  - редактирование расписания.

- `handlers/recurring_income.py`
  - recurring income с аналогичным flow.

- `handlers/cashback.py`
  - несколько conversation-сценариев:
    - карты (add/edit/delete),
    - cashback categories (add/delete),
    - cashback rules (add/edit/delete).

## 3.6. Права доступа в Telegram-flow

Проверки прав централизованы через `utils.permissions.has_permission`.

- `owner`
  - полный доступ (приглашения, роли, удаление проекта, изменения данных).
- `editor`
  - изменение расходов/категорий/бюджета, но без управления участниками.
- `viewer`
  - только просмотр.

На личном контуре (`project_id=None`) операции доступны владельцу данных (проверка ролей не применяется).

## 3.7. Особенности интеграции recommendation в handler

`handlers/recommendations.py`:

- строит `RecommendationPipeline` с Postgres-репозиториями;
- собирает `RecommendationRequest` из расходов/доходов текущего периода;
- отправляет пользователю top-N рекомендаций;
- сохраняет feedback events (`shown`, `liked`, `disliked`, `dismissed`).

Детали алгоритмов — в `06_RECOMMENDATION_MODULE_RU.md`.
